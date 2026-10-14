---
name: crisprme
description: Install CRISPRme from scratch, run off-target searches for CRISPR guide RNAs (variant- and haplotype-aware, or directly against a personal diploid genome assembly), build search indexes for other genomes (incl. non-human), other nucleases/PAMs or a custom VCF cohort, validate/cross-check pipeline test results and pre-flight input files, and summarize completed search results into a risk report or a per-individual card. Use when asked to install/set up CRISPRme, search for off-target sites, run CRISPRme, search a personal/diploid genome assembly, assess guide RNA specificity, use a non-SpCas9 nuclease, a non-human genome or their own variant data, validate a CRISPRme install/pipeline/inputs, or summarize/interpret CRISPRme results.
---

# CRISPRme

CRISPRme predicts off-target sites for CRISPR guide RNAs, incorporating population genetic
variants so results reflect individual/haplotype-level risk, not just the reference genome.

**This skill targets CRISPRme+ v2.7.9** (released 2026-10-11), developed at
`github.com/pinellolab/crisprme-plus`. The original `pinellolab/CRISPRme` repo is
maintenance-only (final release 2.1.14), and **Bioconda's `crisprme` package still installs that
old 2.1.x line** — don't use it for new installs. CRISPRme+ releases often; if the installed
version differs from v2.7.9, see "Notes" at the end before trusting the flags below.

This skill covers:
- **Installing CRISPRme+** (container image + reference data), for a user starting from scratch.
- `complete-search` — the real, genome-wide off-target search. Pre-flight-validates its inputs and
  automatically builds a shareable HTML report at the end.
- `complete-test` — a smoke test of an install against the index the user downloaded.
- `validate-test` — cross-checks a (special, on-demand-build) `complete-test` run against an
  independent brute-force search.
- `assembly-search` — searches a personal diploid genome assembly (two haplotype FASTAs) directly,
  instead of inferring variants from a reference genome + VCF.
- **Other genomes, nucleases and variant data** — non-human genomes, non-NRG PAMs (SaCas9,
  Cas12a, …) and a user's own VCF cohort, via `build-index-only`.
- **Analyzing a completed run's results** — CRISPRme's own `report.html`,
  `scripts/analyze_results.py` for a plain-language summary in the terminal, and
  `generate-personal-card` for one individual's private off-targets.

## How this skill calls CRISPRme

Every CRISPRme command goes through **`scripts/crisprme_cmd.sh <crisprme.py args...>`** (and
`scripts/run_crisprme_job.sh`, which wraps it for background jobs) — never call `crisprme.py`,
`docker run` or `apptainer run` directly. The wrapper reads `./.crisprme_runtime` in the current
directory to decide how to run CRISPRme:

- `apptainer` — the official image as a `.sif` file (typical on HPC/shared servers: no root, no
  Docker daemon; `singularity` works too),
- `docker` — the official `pinellolab/crisprme:<version>` image (laptops/workstations),
- `native` — an existing conda env with CRISPRme+ installed from source.

Two rules follow from this:
- **Always run from the CRISPRme data directory** — the folder holding `.crisprme_runtime`,
  `Genomes/`, `genome_library/`, `Annotations/`, `PAMs/`, `Results/`, and this skill's `runs/`.
  `scripts/...` paths in this document mean this skill's scripts folder; call them by their full
  path if the data directory is elsewhere.
- **Every input file must be inside the data directory.** For container runtimes it is the only
  folder the container can see (mounted at `/DATA`). Pass paths relative to it (`Genomes/hg38`,
  `guides/sg1617.txt`); the wrapper rewrites absolute paths under it and refuses absolute paths
  outside it — if that happens, copy the file in (a symlink pointing outside won't work either;
  a hardlink on the same filesystem does).

`scripts/crisprme_cmd.sh --show-runtime` prints the configured runtime; `scripts/crisprme_cmd.sh
--version` should print `v2.7.9` (or whichever version was installed).

## Installing CRISPRme+ (starting from scratch)

**Before setting up anything new, check what already exists.** Run:
```bash
scripts/find_existing_crisprme_installs.sh [extra dirs to search for .sif images]
```
Read-only. It reports a runtime already configured for the current directory, pulled Docker images,
Apptainer `.sif` images (under `.` by default — pass any other folders to search, e.g. a shared
software dir; `$HOME` isn't searched by default because that can take minutes on a network drive),
and every conda env with `crisprme.py` (all envs, not just ones named "crisprme") — each labeled
**CRISPRme+**, **CRISPRme+, pre-2.6** or **legacy 2.1.x**. Show the results to the user and let
them decide. Reuse is cheap: an existing `.sif` or a CRISPRme+ conda env can be registered for a
data directory without pulling or building anything. Legacy 2.1.x envs are not suitable for this
skill, and pre-2.6 CRISPRme+ installs have the old search defaults, the retired CRISTA scorer and
point at a deleted default index — suggest the current image unless the user specifically wants
that older version. Shared servers accumulate near-duplicate installs, so don't create another one
without surfacing this first.

**1. Pick (or create) the data directory and register a runtime.** From the data directory:
```bash
scripts/install_crisprme.sh                               # auto: Docker if reachable, else Apptainer
scripts/install_crisprme.sh --sif /path/to/crisprme_v2.7.9.sif   # reuse an existing image
scripts/install_crisprme.sh --runtime native --env-prefix /path/to/conda/envs/crisprme  # source env
```
The default pulls `pinellolab/crisprme:v2.7.9` — a **~4.9 GB download that becomes a ~4.5 GB
`.sif`** (the image bundles a GPU-capable CRISPR-Bulge scorer env, liftOver, impg, minimap2 and
BEDOPS). Allow ~10–15 minutes and run it with a long timeout. It writes `.crisprme_runtime` and
prints the detected version, and won't overwrite an existing `.crisprme_runtime` unless given
`--force`. Upstream recommends the container for new users; `native` is for someone who already
installed CRISPRme+ from source (`environment.yml`, Python 3.11, then `install_from_source.sh` —
upstream README §1.3). Don't try `mamba install crisprme` — that's the legacy line.

**2. Quick check.** `scripts/crisprme_cmd.sh --version` (expect `v2.7.9`) and
`scripts/crisprme_cmd.sh --help` (lists the subcommands) confirm the runtime works.
`scripts/crisprme_cmd.sh scorer-env check` confirms the CRISPR-Bulge scorer (it should end with
"compute self-test: OK"; in the official image it always does).

**3. Download the reference data.** `download` pulls from a HuggingFace mirror (fast CDN). Two
steps, both run as background jobs:
```bash
# hg38 genome + annotations + PAMs + sample lists + the NRG_3_hg38 reference search index
scripts/run_crisprme_job.sh download dl-ref --what all --path .
# then ONE prebuilt variant index (see below) — only needed for variant-aware searches
scripts/run_crisprme_job.sh download dl-index-HGDP1kGP --what index \
  --index-name NRG_3_hg38+hg38_HGDP1kGP --path .
```
Run the index download only after `dl-ref` is `DONE`. Disk, measured on 2.7.9: **~26 GB for the
reference-only install, plus ~70–90 GB per variant index** (`HGDP1kGP` ≈ 87 GB, `1000G2021` ≈
71 GB; upstream's "~85 GB total" is an underestimate) — so keep **~130 GB free** for the default
setup. On this server `dl-ref` took a few minutes and the default index ~15 minutes. After both, the data
directory has `Genomes/hg38`, `Annotations/`, `PAMs/`, `samplesIDs/`, `Dictionaries/`,
`genome_library/`, plus `list_vcf.txt` and `list_samplesID.txt` — the `--vcf`/`--samplesID` list
files for a variant-aware `complete-search`.

> **Gotcha — `list_vcf.txt` accumulates.** Every `download --what index` *appends* its dataset to
> `list_vcf.txt` / `list_samplesID.txt`. With two variant indexes installed, a search given
> `--vcf list_vcf.txt` searches **both** datasets. When more than one variant index is installed,
> write a one-line list file per dataset and pass that instead, e.g.
> `echo hg38_HGDP1kGP > vcf_HGDP1kGP.txt` and
> `echo hg38_HGDP1kGP.samplesID.txt > samplesID_HGDP1kGP.txt`. (The dataset name is the part of
> the index name after `+`.)

**Which variant index?** Ask the user if they have a preference; if not, use the default. All are
SpCas9 (NRG PAM = NGG + NAG, up to 2 bulges) on hg38, with searchable indels and SNP+SNP /
SNP+indel co-occurrence:

| `--index-name` | Variants from | Gives you |
|---|---|---|
| `NRG_3_hg38+hg38_HGDP1kGP` **(default)** | HGDP (925) + 1000 Genomes (3,166) = 4,091 people, genotyped and jointly re-phased | CONFIRMED same-haplotype combinations + named carriers throughout — covers most use cases |
| `NRG_3_hg38+hg38_1000G2021` | 1000 Genomes 2021 (3,202 people), phased | the same resolution from a single, well-known panel |
| `NRG_3_hg38+hg38_HPRC` | HPRC pangenome, 232 assembly-derived genomes | the same resolution, plus variation short-read panels miss |
| `NRG_3_hg38+hg38_mega` | 1000G-2021 + HGDP + gnomAD v4.1 + TOPMed + All of Us (frequencies only) | the widest allele-frequency coverage, but **no per-person data** — every multi-variant hit is PUTATIVE; use as a worst-case escalation after a genotyped-index run |

`NRG_3_hg38+hg38_1000G2021_HGDP` (the default before 2.7) **was deleted from HuggingFace** in
2.7.8 — if an older note, script or user asks for it, use `HGDP1kGP` instead. Several indexes can be
installed side by side (one `download --what index` each, ~70–90 GB apiece).

Other `download` targets: `--what assembly --sample <HPRC id>` fetches an HPRC individual's two
haplotype assemblies for `assembly-search` (see below); `--no-genotypes` on `--what index` skips
the genotype store and **loses per-person carriers and variant off-target rows** — don't use it
unless disk is truly short and the user accepts that.

**Download troubleshooting:** "Not enough free disk space" means the data disk itself is short
(the wrapper already keeps HuggingFace's cache at `<data dir>/.hf_cache`, not in a small
`$HOME`). HTTP 429 ("Too Many Requests") errors are retried automatically; if they persist, have
the user export a HuggingFace access token as `HF_TOKEN` in the shell that launches the job
(the wrapper passes it into the container) and relaunch under a new job name — the download
resumes where it stopped.

**4. Smoke test** — `complete-test` (below), once an index is downloaded.

## Before running anything

- Run from the data directory, and make sure a runtime is configured there
  (`scripts/crisprme_cmd.sh --show-runtime`) — see "How this skill calls CRISPRme" above.
- **These subcommands can be long-running (minutes to many hours) and memory-heavy.** Never run
  them in the foreground / never block waiting on them. Always launch through
  `scripts/run_crisprme_job.sh`, which backgrounds the process and tracks status through marker
  files. Report the job name back and tell the user they can **just ask you** to check on it at any
  time — that is the point of the skill, so don't hand them a script to run as the primary way to
  follow their own job. (Mention `scripts/check_run_status.sh <job>` only as a self-service extra,
  for when no session is open.) Don't sit in a polling loop yourself.
- Quick, read-only calls like `--version`, `<subcommand> --help`, `scorer-env check` or
  `cosmic-license status` can go through `scripts/crisprme_cmd.sh` directly.
- **Memory:** a genome-wide *variant-aware* search needs **at least 64 GB of RAM** (peaks ~68–75 GB
  on the default index); 16–32 GB will be killed by the OOM killer (exit code 137). Reference-only
  or single-chromosome searches fit in ~16 GB. With Docker Desktop the limit is set under
  Settings → Resources → Memory; on Linux/Apptainer the container uses host memory directly.
- If more than one job might be running at once on this server, mention that to the user —
  CRISPRme runs are RAM-heavy and concurrent runs can contend for memory.
- Job names must be unique — `run_crisprme_job.sh` refuses to start if `runs/<job_name>/` already
  exists, rather than silently overwriting a previous job's tracking files. Pick a fresh, specific
  name per job (e.g. include the date or guide name), don't reuse generic ones like `test`.

## Running a real search: `complete-search`

Don't just collect all the flags below up front — they fall into tiers. Ask about tier 1, state
your assumption for tier 2 (let the user correct it), quickly check tier 3, and only bring up
tier 4 if the user's request already implies it.

**Tier 1 — always ask, no default makes sense:**
- **Guide sequence(s) to search**, or a target region/BED to extract guides from
  (`--guide` / `--sequence`) — this is the actual question being asked. A guide file holds one
  guide per line as the spacer followed by `N`s for the PAM positions (e.g.
  `CTAACAGTTGCTTTTATCACNNN` for a 20-nt spacer with NRG/NGG).
- **Reference genome build** (`--genome`) — determines which installed reference to point at
  (`Genomes/hg38` after a standard download; the prebuilt indexes are hg38-only).

**Tier 2 — fill in and state the assumption, don't interrogate the user for these:**
- **Search depth** (`--mm`, `--bDNA`, `--bRNA`, `--max-total-edits`) — propose CRISPRme+'s
  recommended default, **4 mismatches + 1 DNA bulge + 1 RNA bulge** (`--mm 4 --bDNA 1 --bRNA 1`;
  `--max-total-edits` then defaults to 6, which covers it). Say so explicitly — it is a biology
  judgment call and the user may want deeper or shallower. This default sits in the CRISPR-Bulge
  scorer's validated single-bulge domain. **If the user wants a deeper search, raise
  `--max-total-edits` to the sum** (`--mm 6 --bDNA 2 --bRNA 2 --max-total-edits 10`), otherwise
  alignments over the budget are silently pruned. Negative values are rejected. Sites with ≥2
  bulges get no CRISPR-Bulge score (shown as `-`) — read CFD for those. Before launching anything
  deeper than the default, run upstream's cost estimator and pass its risk tier on to the user:
  `scripts/crisprme_cmd.sh --exec python /opt/conda/opt/crisprme/PostProcess/search_budget.py --mm 6 --bdna 2 --brna 2`
  (add `--variants-per-kb 1` for a variant-aware search). `OK` is routine; `HEAVY` means warn
  about runtime/disk; `EXTREME` (~200 GB of intermediates, OOM risk — e.g. 6 mm + 2 + 2) means
  strongly suggest shallower settings. Use only the tier: its RAM figure covers post-analysis, not
  the ~64 GB a genome-wide variant search needs. (On a `native` install the script lives under
  the env's `opt/crisprme/PostProcess/`.)
- **PAM / Cas system** (`--pam`) — default to `PAMs/20bp-NRG-SpCas9.txt` (SpCas9 NGG + NAG,
  matching the prebuilt indexes) unless the user names a different system. A different PAM
  (Cas12a, SaCas9, …) has **no prebuilt index** — one must be built first (see "Beyond the
  prebuilt indexes" below: ~10 minutes via the kit route on the default panel, hours from a raw
  VCF); flag that cost before starting.
- **Job/output name** (`--output`) — auto-generate a fresh, specific one (same rule as job names
  above); let the user rename it if they want.

**Tier 3 — worth a quick check because they change what the search actually does:**
- **Variant-aware search?** (`--vcf` + `--samplesID`) — this is CRISPRme's whole differentiator
  over a plain aligner. Don't silently default to reference-only; ask whether the user wants
  population/haplotype-level results, and if so which variant index (whichever of the table above
  are installed under `genome_library/`). Mind the `list_vcf.txt` gotcha above.
- **Population-level (default) or `--per-sample`?** By default CRISPRme+ runs a
  *population-level* analysis: one worst-possible representative per variant window — lossless
  for *detecting* off-targets, works on any index. `--per-sample` resolves each person's actual
  haplotypes: CONFIRMED cis phasing, named carrier samples, exact joint allele frequency — what
  you want for clinical validation or "who carries this?" questions. It needs a genotyped index
  (not `mega`, where it's inert), costs about the same for a single guide, but can become
  intractable on dense panels. It also turns on the large alternative-alignments file
  (override with `--no-alt-alignments`). Ask which the user needs; if unsure, default to
  population-level and mention `--per-sample`.
- **Functional/annotation context?** (`--annotation` / `--gene_annotation`) — after
  `download --what all` the bundled files are `Annotations/dhs+encode_screenv4+gencode+cosmic.hg38.bed.gz`
  (regulatory + gene features; IntOGen cancer-driver flags are merged in automatically) and
  `Annotations/gencode.protein_coding.bed.gz` (nearest gene + `Gene_region`: CDS/UTR/exon/intron/
  intergenic). Default to using both; just confirm.
- **COSMIC cancer annotations are excluded by default** (licence-gated — commercial use needs a
  COSMIC licence). The search prints "COSMIC EXCLUDED from annotation" — that's expected, not an
  error. Only if the user asks for COSMIC: explain the licence terms (free for academic/
  non-commercial use with registration, commercial use needs a QIAGEN licence;
  https://www.cosmickb.org/terms/) and **let the user confirm they hold an appropriate licence
  themselves** before running `scripts/crisprme_cmd.sh cosmic-license enable --accept`. Never
  enable it on your own initiative — it's a persistent legal attestation for the whole data
  directory. `cosmic-license status` / `disable` are safe to run any time.

**Tier 4 — rarely relevant, leave at CRISPRme's defaults unless the user brings it up:** base
editing (`--be-window`/`--be-base`), `--thread` (default 8), `--merge` (default 3),
`--sorting-criteria-scoring` / `--sorting-criteria`, `--full_input_validate` (see below),
`--index-path` (a prebuilt index library elsewhere, e.g. a read-only shared mount),
`--compute-backend` (`cpu` default; `cuda` needs a GPU passed into the container — not wired into
this skill's wrapper, so stay on CPU).

```bash
scripts/run_crisprme_job.sh complete-search sg1617-HGDP1kGP-1013 \
  --genome Genomes/hg38 \
  --pam PAMs/20bp-NRG-SpCas9.txt \
  --guide guide_sg1617.txt \
  --vcf list_vcf.txt --samplesID list_samplesID.txt \
  --annotation Annotations/dhs+encode_screenv4+gencode+cosmic.hg38.bed.gz \
  --gene_annotation Annotations/gencode.protein_coding.bed.gz \
  --mm 4 --bDNA 1 --bRNA 1 \
  --output sg1617-HGDP1kGP-1013 --thread 8
```

Omit `--vcf`/`--samplesID` for a reference-only search; add `--per-sample` for genotype
resolution. CRISPRme writes everything to `Results/<output>/`, and at the end automatically builds
`Results/<output>/<output>_report.zip` (see "Analyzing results") — the user shouldn't need to
navigate this folder themselves.

A variant-aware search with **no matching prebuilt variant index** stops in pre-flight ("No
prebuilt variant index found") — CRISPRme never builds one automatically. Download the index, or
build one with `build-index-only` (long), rather than setting `CRISPRME_ALLOW_ONDEMAND_BUILD`.

## Beyond the prebuilt indexes: other genomes, other nucleases, your own variants

The four downloadable variant indexes are all **human hg38 + SpCas9 NRG**. Anything else needs
an index built locally with `build-index-only` (or, for a different PAM on the published human
panels, the faster kit route below). An index only fits searches with the same genome, PAM and
*maximum* bulges it was built for (the `_<N>_` in its name is `max(bDNA,bRNA)+1`; build for the
deepest search you expect, e.g. `--bDNA 2 --bRNA 2` → `_3_`, which also serves 1-bulge searches).
CRISPRme never builds one silently, so always tell the user the extra time and disk first.

PAM files are one line, `<spacer N's + motif> <signed PAM length>` — positive = 3′ PAM (SpCas9),
negative = 5′ PAM (Cas12a). `download` ships only `20bp-NGG-SpCas9.txt`, `20bp-NRG-SpCas9.txt` and
`20bp-NNN-NO-PAM.txt` (`--what pams`, included in `--what all`); write any other one yourself,
named `<length>-<motif>-<Cas>.txt` (the third `-` field is read as the nuclease label):
```bash
printf 'NNNNNNNNNNNNNNNNNNNNNNNGRRT 6\n' > PAMs/21bp-NNGRRT-SaCas9.txt   # SaCas9, 3' PAM
printf 'TTTVNNNNNNNNNNNNNNNNNNNNNNN -4\n' > PAMs/23bp-TTTV-Cas12a.txt     # Cas12a, 5' PAM
```
Only the first line is read — use an IUPAC motif (e.g. `NRG` = NAG + NGG) to cover several PAMs.
Each guide must be exactly as long as the motif (the first field of the PAM file), with `N`s in
the PAM positions — 20-nt spacer + `NNN` for SpCas9; 21-nt spacer + `NNNNNN` for the SaCas9 file
above; `NNNN` + 23-nt spacer for the Cas12a one (27 characters each). Check
`awk '{print length($1)}' <pamfile>` against each guide's length before launching — the
pre-flight catches a mismatch, but its suggested fix ("append N's") is misleading when it's
actually the spacer that is the wrong length.

### A non-human (or non-hg38) genome — reference-only search

```bash
# 1. fetch the genome from UCSC by assembly name (e.g. susScr11 = pig, mm39 = mouse); in a new
#    data folder also fetch the PAM files (`--what all` would add the hg38 bundle you don't need)
scripts/run_crisprme_job.sh download dl-susScr11 --what genome --ref susScr11 --source ucsc --path .
scripts/crisprme_cmd.sh download --what pams --path .
#    (or --source url --url <link to a .fa.gz> for a genome UCSC doesn't host)
# 2. build its search index for the PAM and bulge depth you'll search with
scripts/run_crisprme_job.sh build-index-only idx-susScr11-NGG \
  --genome Genomes/susScr11 --pam PAMs/20bp-NGG-SpCas9.txt --bDNA 1 --bRNA 1 --thread 16 --path .
# 3. search as usual, without --vcf/--samplesID (and without the hg38-only annotation files)
scripts/run_crisprme_job.sh complete-search pig-sg1-1013 --genome Genomes/susScr11 \
  --pam PAMs/20bp-NGG-SpCas9.txt --guide guide_pig.txt --mm 4 --bDNA 1 --bRNA 1 --output pig-sg1-1013
```

The genome lands in `Genomes/<ref>/` split one FASTA per chromosome. Measured for the pig
genome on 16 threads: download ~5 min, index (1 bulge) ~11 min, a 4/1/1 search ~20 min. Chromosome
names must be `chr`-prefixed (UCSC assemblies are). The hg38 annotation bundle and variant
indexes don't apply to other species — results come without functional annotation unless the user supplies a matching
BED (`--annotation`, 4th column = feature name; `--gene_annotation` for nearest gene).

### Your own variant dataset (a cohort VCF, or a non-hg38 genome's variants)

1. **Prepare the VCF** (one multi-chromosome `.vcf.gz` is fine — 2.7.9 splits it per chromosome
   itself — or per-chromosome files named with a dot-separated `chrN` segment, e.g.
   `cohort.chr1.vcf.gz`): `chr`-prefixed names matching the genome, `FILTER` = `PASS`, numeric
   `INFO/AF`, `FORMAT/GT`, no structural variants (`<DEL>`, breakends). A typical clean-up:
   `bcftools view -f PASS in.vcf.gz | bcftools view -e 'ALT[0]~"<"' -Oz -o VCFs/hg38_mycohort/mycohort.vcf.gz`
   (bcftools is in the image: `scripts/crisprme_cmd.sh --exec bcftools …`). Put it in its own
   folder under `VCFs/`, named `<genome>_<dataset>` (e.g. `VCFs/hg38_mycohort/`).
2. **Write the sample list** `samplesIDs/hg38_mycohort.samplesID.txt` — tab-separated, header
   `#SAMPLE_ID	POPULATION_ID	SUPERPOPULATION_ID	SEX`, one row per sample in the VCF (use
   placeholders like `NA` for unknown population/sex). Listing a sample that isn't in the VCF is a
   hard error. Then a one-line listing file naming it, e.g.
   `echo hg38_mycohort.samplesID.txt > samplesID_mycohort.txt`, and `echo hg38_mycohort > vcf_mycohort.txt`.
3. **Pre-flight the inputs** — this is the case `--full_input_validate` exists for. The cheapest
   way is a throwaway `complete-search` with `--full_input_validate` that will stop at the missing
   index after validating; read its `[OK]/[WARN]/[ERROR]` report and fix errors first.
4. **Build** (hours for a genome-wide cohort; the genome enrichment writes >100 GB of temporary
   files — check free disk with the user first):
   ```bash
   scripts/run_crisprme_job.sh build-index-only idx-mycohort \
     --genome Genomes/hg38 --pam PAMs/20bp-NRG-SpCas9.txt --bDNA 2 --bRNA 2 --thread 16 \
     --vcf vcf_mycohort.txt --samplesID samplesID_mycohort.txt --path .
   ```
   **`--samplesID` is required in practice**: without it the build silently produces a legacy
   "dicts-only" index with no fast post-analysis tiers. The result is
   `genome_library/NRG_3_hg38+hg38_mycohort/` (+ `_INDELS`) plus its `Dictionaries/` tiers. A
   SNP-only VCF is fine (the indel index is skipped).
5. **Search** with `--vcf vcf_mycohort.txt --samplesID samplesID_mycohort.txt` like any other
   variant-aware search. `--per-sample` needs genotypes in the VCF; only phased genotypes give
   CONFIRMED same-haplotype combinations (unphased ones still name carriers, marked PUTATIVE).

### A different PAM on the published human panels (fast "kit" route)

To screen e.g. SaCas9 or Cas12a against the same HGDP+1kGP (or mega) variants, don't rebuild
from VCFs — upstream publishes the PAM-independent enriched genome as a "kit". Needs the normal
index download for that dataset first (its `Dictionaries/` are reused at search time):
```bash
# 1. fetch + unpack the enriched-genome kit (~1 GB download, a few GB unpacked)
scripts/run_crisprme_job.sh exec kit-HGDP1kGP hf download lucapinello/crisprme-data \
  build-inputs/hg38_HGDP1kGP.tar.gz --repo-type dataset --local-dir .
tar xzf build-inputs/hg38_HGDP1kGP.tar.gz      # -> Genomes/hg38+hg38_HGDP1kGP{,_INDELS}/
# 2. index it for the new PAM (N = max(bDNA,bRNA)+1; <MOTIF> = PAM letters only, e.g. NNGRRT)
scripts/run_crisprme_job.sh exec idx-HGDP1kGP-SaCas9 crispritz.py index-genome \
  hg38+hg38_HGDP1kGP Genomes/hg38+hg38_HGDP1kGP/ PAMs/21bp-NNGRRT-SaCas9.txt -bMax 3 -th 16
scripts/run_crisprme_job.sh exec idx-HGDP1kGP-SaCas9-indels python \
  /opt/conda/opt/crisprme/PostProcess/pool_index_indels.py \
  Genomes/hg38+hg38_HGDP1kGP_INDELS/ PAMs/21bp-NNGRRT-SaCas9.txt NNGRRT hg38 hg38_HGDP1kGP 3 16
# 3. search with that PAM and the dataset's list files
```
Run step 2's two jobs one after the other (wait for `DONE`; measured ~7 min for the SNP index on
16 threads, and a genome-wide SaCas9 search on it took ~35 min). `-bMax` sets the `_<N>_` in the
index name directly; use 3 (serves searches with up to 2 bulges, like the published indexes —
verified: a 1-bulge search ran on the `_3_` index). `exec` jobs run any program from the
CRISPRme runtime (`scripts/crisprme_cmd.sh --exec …` for quick ones). Kits exist only for
`HGDP1kGP` and `mega`; for 1000G-2021 or HPRC, or to reproduce a kit, see upstream
`docs/PRECOMPUTED_INDEXES.md`.

## Input validation (automatic on `complete-search`)

`complete-search` validates its own inputs before launching the pipeline — this is CRISPRme's own
behavior (not something this skill adds), but it changes what a fast `FAILED` job usually means:

- **Lightweight tier — always runs, no flag needed.** Cheap header/first-record checks: genome
  FASTA headers, VCF filenames carry a `chrN` token matching the genome, each VCF is gzip-valid
  with a proper `#CHROM` header and an `AF` INFO field, `.tbi` indexes are present, `--samplesID`
  sample names appear in the VCF header (**listing samples that aren't in the panel is a hard
  ERROR** since 2.7), PAM/guide file basics, gene-annotation file is gzip-compressed. Seconds.
- **Full tier — opt-in via `--full_input_validate`.** Reads every VCF record: full chromosome
  coverage, AF/FILTER consistency, FILTER PASS ratio, POS bounds against the genome FASTA,
  high-allele-count multiallelic sites, breakend notation, duplicate records, mixed GT phasing,
  indels too close to a chromosome start. Slower (scales with VCF size), so only suggest it when
  the user is debugging a suspicious result or setting up a new/unfamiliar VCF dataset — not on
  every routine search (and it's moot for the prebuilt indexes, which carry no raw VCFs).
- **A validation error aborts before the pipeline starts** (exit code 1) with an
  `[OK]`/`[WARN]`/`[ERROR]` report. If a `complete-search` job goes `FAILED` within seconds rather
  than after real runtime, check the log for this report first — it says exactly what's wrong.
  `[WARN]` lines don't block the run.
- A pipeline failure later on prints "Failed during stage: …" plus the tail of
  `Results/<output>/log_error.txt` into the job log — start there.

## Smoke-testing an install: `complete-test`

Runs the built-in example guide (sg1617) against **whichever prebuilt index is already
downloaded** — a variant index if one is present (reference-only otherwise), with
`--mm 2 --bDNA 1 --bRNA 1`, population-level, into `Results/crisprme-test-out/`. It ends with
"complete-test PASSED: …" when it produced results — about 15 minutes on 16 threads against the
default index.

```bash
scripts/run_crisprme_job.sh complete-test smoke-1013 --thread 8
```

- **It needs downloaded data.** With no index it prints how to download one and exits *0* without
  testing anything; `run_crisprme_job.sh` catches that and marks the job `FAILED`.
- **It's genome-wide.** In 2.7.9 the smoke test ignores `--chrom` (despite the upstream README),
  so on a variant index it needs the same ~64 GB of RAM as a real search. On a smaller machine,
  test with the reference-only index instead.
- **It tests whichever index sorts first.** It picks the alphabetically first index in
  `genome_library/` (preferring variant ones) and runs the SpCas9 example guide against it. If
  the folder also holds a custom-PAM index (e.g. `NNGRRT_…` or `NGG_…`, which sort before
  `NRG_…`) it tests that one instead and fails in pre-flight with a guide-length `[ERROR]`.
  In a folder with non-NRG indexes, skip `complete-test` and use a small real
  `complete-search` as the end-to-end check.
- **It runs once per data directory**: if `Results/crisprme-test-out` (or an older
  `crisprme-test-out_*`) exists it prints "Complete-test already run once" and exits 0 (the job
  is marked `FAILED`). With the user's OK, move the old folder aside first.
- A real, small `complete-search` for the user's own guide is an equally good end-to-end check.

## Cross-checking against brute force: `validate-test`

Compares CRISPRme's off-targets against an exhaustive brute-force aligner (exact set equality) —
a correctness check, mostly used by upstream CI. **It only works on output of the special
on-demand-build test mode, not on the smoke test above:**

```bash
CRISPRME_ALLOW_ONDEMAND_BUILD=1 CRISPRME_SKIP_HEAVY=1 \
  scripts/run_crisprme_job.sh complete-test bench-chr22-1013 --chrom chr22 --vcf_dataset 1000G --thread 8
# after that job is DONE:
scripts/run_crisprme_job.sh validate-test validate-chr22-1013 --chrom chr22
```

- The on-demand mode downloads chr22 test data (raw 1000 Genomes 2019 VCFs, genome, annotations)
  and **builds small indexes on the fly** — one `complete-search` per registered benchmark into
  `Results/crisprme-test-out_<benchmark>/`. `CRISPRME_SKIP_HEAVY=1` skips the 2-bulge benchmarks,
  which need well over 16 GB of RAM; leave it unset on a big machine to run them all.
- `validate-test` only supports `--vcf_dataset 1000G` (the default), and reports
  "Validation summary: N passed, M failed, K skipped"; any failure exits non-zero. Measured with
  `CRISPRME_SKIP_HEAVY=1` on 16 threads: the benchmark `complete-test` ~20 min, `validate-test`
  under a minute, "2 passed, 0 failed, 2 skipped" (the skipped ones are the heavy benchmarks that
  weren't run — expected, not a problem).
- This mode deliberately exercises the legacy build-from-raw-VCF path, not the prebuilt-index
  path real searches use. That's fine for this purpose, but explain it to the user and only run it
  when they actually want the brute-force cross-check; for "does my install work?" the smoke
  test is enough. Same "already run once" rule as above (move old `crisprme-test-out*` aside).

## Searching a diploid genome assembly directly: `assembly-search`

**What it's for:** the individual already has a fully assembled personal diploid genome — two
haplotype assemblies (paternal/maternal, HPRC-style) — instead of a reference genome + VCF to
infer variants from. `assembly-search` searches each haplotype directly, lifts the predictions to
hg38 and reconciles them. **No `--vcf` is used or accepted** — don't ask about variant
datasets/populations for this path.

**Getting an assembly.** For an HPRC individual, one background download fetches both haplotypes'
genome + chain + chromAlias into `Assemblies/<id>/` and registers it:
```bash
scripts/run_crisprme_job.sh download dl-HG01255 --what assembly --sample HG01255 --path .
```
A user's own assembly can be registered through the web Data Manager (a `.zip`/`.tar.gz`
bundle), or passed as the six explicit paths below.

**Flags:**
- `--assembly-individual <name>` — a registered `Assemblies/<name>/` (its `metadata.json` supplies
  the genome/chain/chromAlias paths). **Or** the six explicit paths instead:
  `--genome-paternal`/`--genome-maternal` (per-chromosome FASTA folders), `--chain-paternal`/
  `--chain-maternal` (liftOver chains vs GRCh38), `--chrom-alias-paternal`/`--chrom-alias-maternal`
  (tab-separated, columns `# assembly`, `ucsc`, `genbank`).
- `--guide`, `--pam`, `--mm` (required), `--bDNA`, `--bRNA` — same meaning as `complete-search`
  (no `--sequence` option here). Suggest the same 4/1/1 default.
- `--max-total-edits` — defaults to `mm+bDNA+bRNA` here (no extra cap), unlike `complete-search`.
- `--merge` (default 3) — also the locus-clustering tolerance used to reconcile the two
  haplotypes, so it must be the same for both; don't let the user vary it per haplotype.
- `--annotation`, `--gene_annotation` — same bundled files as `complete-search`; applied to every
  reconciled site that has an hg38 coordinate (adds `Annotation_*` columns, the closest gene and
  `Annotation_gene_region`). Default to using both.
- `--output` — base name; `--thread` (default 8), `--debug`.

The image bundles everything this needs (liftOver, impg 0.5, minimap2, BEDOPS). On a **native**
install, check `which liftOver impg minimap2 closest-features` first — it fails fast if any is
missing.

**Outputs.** Each haplotype's normal `complete-search` results land in `Results/<name>_paternal`
and `Results/<name>_maternal` (each with its own report). The reconciled result is
`Results/<name>_combined/<name>_combined_hg38.tsv` plus `<name>_combined_report.zip` (a combined
`report.html` with both per-haplotype reports bundled inside). Each reconciled site's `origin`:
- `both` — found on both haplotypes at the same hg38 locus (homozygous-equivalent),
- `paternal_only` / `maternal_only` — found on one haplotype (heterozygous-equivalent),
- `both_haplotype_private` — no hg38 equivalent, but impg's direct haplotype-to-haplotype
  alignment shows the *same* site on both haplotypes (a homozygous site invisible to any
  reference-based search).
The run log also prints each haplotype's remaining non-mappable count (sites with no hg38
equivalent at all — likewise invisible to reference-based searches).

**Runtime shape:** two full `complete-search` pipelines back-to-back (each also builds that
haplotype's search index the first time) plus reconciliation — budget well over double a single
`complete-search`. Launch it like any other subcommand:
```bash
scripts/run_crisprme_job.sh assembly-search hg01255-sg1617-1013 \
  --assembly-individual HG01255 \
  --guide guide_sg1617.txt --pam PAMs/20bp-NRG-SpCas9.txt --mm 4 --bDNA 1 --bRNA 1 \
  --annotation Annotations/dhs+encode_screenv4+gencode+cosmic.hg38.bed.gz \
  --gene_annotation Annotations/gencode.protein_coding.bed.gz \
  --output hg01255-sg1617-1013 --thread 8
```

**Retry behavior:** if a haplotype's search already completed with the *same* parameters, a re-run
with the same `--output` reuses it instead of re-running hours of search — useful after a
reconciliation-only failure. It refuses only if the *combined* TSV already exists — pick a new
`--output` or remove that file to re-run reconciliation.

## Analyzing results

**CRISPRme's own report is the primary deliverable.** Every finished `complete-search` (and each
`assembly-search` haplotype) writes `Results/<output>/<output>_report.zip`. Unzipped,
`report.html` is a fully offline page: run summary + mismatch/bulge matrix, a **recommended
~100-site validation panel** (`data/panel_top100.tsv`, for a targeted-NGS / rhAMP-Seq
confirmation assay), the top-1000 annotated off-targets, and per-tier TSVs under `data/`.
Point the user to it (it's the thing to share with collaborators). Regenerate it with
`scripts/run_crisprme_job.sh generate-report <job> --result-dir Results/<output>` if needed.

Key things to explain when presenting results (they're also in the report):
- **Non-SpCas9 nucleases (SaCas9, Cas12a, …) get no CFD or CRISPR-Bulge score** — both models
  are trained on SpCas9 — so their report and panel are ranked by mismatches + bulges only. Say
  so; don't present the missing score as "no risk".
- **CFD** is the primary score (≤3–4 mismatches is its design range; don't compare CFD across
  searches with different thresholds or panels). **CRISPR-Bulge** is a second, ML-based score on
  its own scale (bands 0.5 / 0.2 / 0.1); `-` means not scored (≥2 bulges), not "no risk".
- **`Observed`**: `reference` (in the reference genome — essentially everyone carries it),
  `N carrier(s)` (named people carry it), `observed` (a single real variant), `putative` (a
  multi-variant combination nobody is confirmed to carry in cis — a worst-case reconstruction).
- **Red "no unambiguous on-target" banner**: the guide has more than one perfect match, so every
  perfect-match site is a candidate on-target. Flag this prominently — it usually means pick a
  different guide.
- A MAF of `1e-05` is a display floor ("present, frequency ~0"), not a measurement.
- **Population-level runs report one worst-case representative per site** — so the
  *per-population site totals* are upper bounds (measured ~1.5x the `--per-sample` totals). Be
  precise about what that does and does not cover, because it is easy to over-apply:
  - **A single-variant site's `Observed` carrier count is exact in both modes** — verified
    identical on every shared validation-panel site across a population-level and a
    `--per-sample` run of the same guide. Don't hedge it as an upper bound.
  - What `--per-sample` actually adds: CONFIRMED cis phasing for **multi-variant** sites (which
    otherwise all stay `putative`), the named carrier samples, exact joint allele frequency, and
    meaningful `summary_by_samples` per-person totals.
  - So "which individuals carry this exact off-target?" needs `--per-sample`; "how many people
    carry this one variant?" does not.

For a quick terminal summary, `scripts/analyze_results.py` reads a `Results/<name>/` folder:
```bash
scripts/analyze_results.py Results/sg1617-HGDP1kGP-1013 --top 10
```
It prints the run's mode/index/version, total off-targets with the mismatch/bulge breakdown and
variant-only counts, the perfect-match (on-target ambiguity) check, population totals, SNP+indel /
SNP+SNP co-occurrence counts (CONFIRMED vs PUTATIVE), and the top-N sites of the recommended
validation panel with their `Observed` status, gene and gene region.
- `--guide <sequence>` — required if the run searched more than one guide.
- `--method cfd|crispr-bulge|fewest` (default `cfd`) — which of CRISPRme's three rankings the
  summary-file counts use (`crista` is accepted for runs from CRISPRme 2.5 and earlier).
- `--top N` (default 10).
- **Multiple guides in one run get a ranking**: a comparison table (total off-targets, 0–2
  mismatch off-targets, variant-only count per guide) ranked by fewest near-exact off-targets, as
  a "lowest apparent risk" call-out. It's a quick proxy that ignores scores and genomic context —
  present it as a starting point, and point to each guide's report for the real assessment.

It only reads small files (the `summary_by_*` / `PopulationDistribution` summaries, the
co-occurrence TSVs, and the report zip's panel table) — safe and fast even on genome-wide output.

For `assembly-search`, pass the `_combined` folder: it summarizes origin counts and the top-N
reconciled sites by CFD (with closest gene / gene region when annotated), and points to the
combined report. `Results/<name>_paternal` / `_maternal` can be analyzed individually like any
`complete-search` output.

### One individual's view: `generate-personal-card`

For "what's the off-target picture for *this* person?" (e.g. a patient-like individual in the
panel). It needs a **`--per-sample` run** on a genotyped index — on a population-level run the
per-person lists are worst-case reconstructions, so don't use it there (re-run with
`--per-sample` first, and say why).
```bash
scripts/crisprme_cmd.sh generate-personal-card --result_dir Results/<output> \
  --guide_seq CTAACAGTTGCTTTTATCACNNN --sample_id NA20355
```
- `--guide_seq` is the guide exactly as searched, including the PAM `N`s (see
  `Results/<output>/.guides.txt`).
- **Check the sample ID first** — it must appear in the first column of the run's samplesID
  file (`grep -w <id> samplesIDs/<dataset>.samplesID.txt`). An unknown or misspelled ID is
  *not* an error: it silently writes an empty table and exits 0, which looks exactly like
  "no private off-targets". Matching is also by substring, so use complete IDs.
- Takes seconds (it queries the run's database). Writes into the run folder:
  `<output>.<sample>.<guide>.private_targets.tsv` — the off-targets **only this individual
  carries** (often empty; that's a normal, good result) — plus six plots under `imgs/`
  (`*.<sample>.personal.png` = every variant off-target the person carries, `*.private.png` =
  the private ones, for CFD / CRISPR-Bulge / fewest-mismatch rankings). The person's total
  count is in `summary_by_samples` (`Targets in Sample`), which `analyze_results.py` reports.

## Checking on a job

When the user asks how a job is going — in any wording — run this yourself and answer in plain
language; don't redirect them to the command. Use `scripts/check_run_status.sh <job_name>` (the
name you gave as the second argument to `run_crisprme_job.sh`). Reports current status (`RUNNING`/`DONE`/`FAILED`), whether the process is
still alive, and the last 15 lines of the log. Re-run this on request rather than assuming a job
has finished — do not guess completion from elapsed time. CRISPRme buffers much of its output, so
an empty or quiet log early on is normal; the stage log `Results/<output>/log.txt` (tab-separated
`<stage> Start/End` lines) shows finer progress for a running search.

This skill's own tracking files live under `runs/<job_name>/` (`status`, `run.log`, `pid`,
`exit_code`, `command`) — separate from CRISPRme's own output under `Results/`.

## Notes / things to double check

- Flags and behavior here were checked against CRISPRme+ **v2.7.9** (source at the v2.7.9 tag,
  plus the published `pinellolab/crisprme:v2.7.9` image run through Apptainer on 2026-10-13). If
  `scripts/crisprme_cmd.sh --version` reports something else, confirm flags with
  `scripts/crisprme_cmd.sh <subcommand> --help` before relying on this document, and check the
  upstream `CHANGELOG.md` — CRISPRme+ ships several releases a week at times.
- **Don't trust exit code alone.** `run_crisprme_job.sh` also greps the log for `ERROR:`,
  `CRISPRme run failed`, `Traceback`, and `complete-test`'s exit-0 non-runs ("already run once",
  "No prebuilt index found") before marking a job `DONE` — keep doing that if working outside the
  script.
- A search that degrades to CFD-only because the ML scorer is unavailable prints a loud warning
  and leaves the CRISPR-Bulge column at `-1`. In the official image this shouldn't happen; if it
  does, run `scripts/crisprme_cmd.sh scorer-env doctor` and tell the user.
- **Apptainer runs with `--cleanenv`** (in `crisprme_cmd.sh`): host environment variables are not
  passed into the container except `HF_TOKEN` and `CRISPRME_*` tuning variables (e.g.
  `CRISPRME_MAX_MEM_GB`, `CRISPRME_INDEL_SNP=0` to turn off SNP+indel co-occurrence). This is
  deliberate — a host `SSL_CERT_FILE` pointing at a path that doesn't exist in the image made every
  HuggingFace download fail on this server.
- Every NRG search with bulges prints "WARNING: PAM motif 'NRG' is a partially-degenerate,
  odd-length motif used with bulges. This combination can crash …". It's informational: the
  CRISPRitz in the 2.7.9 image (v2.9.0) contains that fix, and NRG + bulges is exactly what the
  prebuilt indexes are built for. Don't change the PAM or drop bulges because of it.
- The removed `--fast` / `--full` flags (CRISPRme+ 2.5.x only) now just print a warning;
  `--per-sample` replaced `--full`.
- **Web interface.** CRISPRme+ also has a local point-and-click UI (`crisprme.py web-interface`,
  served at port 8080; on a headless server it needs `-p 8080:8080` for Docker or an SSH
  port-forward). It's a long-running server, not a job, so this skill doesn't launch it — if
  the user prefers clicking, point them to upstream `docs/DOCKER_QUICKSTART.md`. Results from CLI
  and web runs share the same `Results/` layout, so everything here works on either.
- CRISPRme+ is licensed under MGB Open Access 1.0 (free for non-commercial academic use;
  commercial use needs a separate licence) — mention it if the user's context looks commercial.
