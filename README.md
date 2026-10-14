# CRISPRme skill

A [Claude Code](https://claude.com/claude-code) **Agent Skill** that runs
[CRISPRme+](https://github.com/pinellolab/crisprme-plus) from plain-language requests:
install it from scratch, run variant- and haplotype-aware off-target searches, and turn the
results into a readable risk summary.

Written for and tested against **CRISPRme+ v2.7.9**.

The skill is a document plus a handful of scripts. It does not wrap or reimplement CRISPRme:
every command it runs is a real `crisprme.py` subcommand, and CRISPRme's own outputs (including
the shareable `report.html`) are the deliverables. What the skill adds is the operational
knowledge around those commands — which questions to ask before a search, what the current
defaults are, how to run hour-long jobs without blocking, and which failure modes look like
success.

---

## What it does

| Ask | What happens |
|---|---|
| "Set up CRISPRme for me" | Scans for existing installs first, then registers the official v2.7.9 container (Apptainer, Docker, or an existing source install) and downloads the reference data and a variant index as background jobs |
| "Check this guide for off-targets" | Asks only about the choices that matter, states its assumptions for the rest, estimates the cost of deep searches, and runs `complete-search` as a background job |
| "What did it find?" | Points at CRISPRme's own report and prints a plain-language summary: counts, on-target ambiguity, variant-driven sites, co-occurring variants, and the recommended validation panel |
| "Who carries these off-targets?" | Switches to `--per-sample` analysis; `generate-personal-card` for one named individual |
| "Does my install work?" | `complete-test` smoke test, or `validate-test` to cross-check against an exhaustive brute-force search |
| "Can it do SaCas9 / pig / my own cohort VCF?" | Builds the needed index via `build-index-only` or the published enriched-genome kit, with the time and disk cost stated up front |
| "Search this person's assembled genome" | `assembly-search` on both haplotypes, reconciled against hg38 |

A worked walkthrough of these paths, with real command output, is in
[`docs/`](docs/) (see **Documentation** below).

---

## Requirements

- **Claude Code** (any recent version).
- **A container runtime**: Docker on a laptop or workstation, or **Apptainer/Singularity** on an
  HPC or shared server (no root needed). A conda environment with CRISPRme+ installed from source
  also works.
- **Disk**: ~4.5 GB for the container image, ~26 GB for the hg38 reference data, and ~70–90 GB
  per variant index. Budget **~130 GB** for a standard variant-aware setup.
- **Memory**: a genome-wide variant-aware search needs **at least 64 GB of RAM** (it peaks around
  68–75 GB). Reference-only or single-chromosome searches fit in ~16 GB.

Bioconda's `crisprme` package is still the old 2.1.x line and is **not** suitable — the skill
expects CRISPRme+ 2.6 or later.

## Install

```bash
git clone <this repo> crisprme-skill

# make it available to Claude Code, either for one project...
mkdir -p <your-project>/.claude/skills
cp -r crisprme-skill <your-project>/.claude/skills/crisprme

# ...or for every project
cp -r crisprme-skill ~/.claude/skills/crisprme
```

Then, from the directory where CRISPRme's data and results should live, ask Claude to set
CRISPRme up — or run the installer yourself:

```bash
cd /path/to/your/crisprme-data-dir
~/.claude/skills/crisprme/scripts/install_crisprme.sh      # pulls the v2.7.9 image
```

That writes a `.crisprme_runtime` file recording how to run CRISPRme in this directory. Every
later command goes through `scripts/crisprme_cmd.sh`, so the rest of the skill works the same
whether CRISPRme runs under Apptainer, Docker, or a source install.

## Layout

```
SKILL.md                            the skill itself: what Claude reads and follows
scripts/
  crisprme_cmd.sh                   runs any crisprme.py command through the configured runtime
  run_crisprme_job.sh               launches a subcommand as a tracked background job
  check_run_status.sh               reports a job's status, liveness, and recent log
  install_crisprme.sh               registers a runtime (container image or conda env)
  find_existing_crisprme_installs.sh  read-only scan for installs already on the machine
  analyze_results.py                turns a finished run into a plain-language risk summary
examples/flagship-search/           real output from a genome-wide variant-aware run
```

`SKILL.md` is the substance. The scripts exist so that Claude never has to improvise a
`docker run` or `apptainer run` invocation, and so long jobs can be launched and checked without
blocking the conversation.

---

## Tested against v2.7.9

Every route below was executed end-to-end on a shared Linux server (88 cores, 1 TB RAM) using
the published `pinellolab/crisprme:v2.7.9` image under Apptainer, on 2026-10-13.

| Route | Result | Wall time |
|---|---|---|
| Container pull + runtime registration (Apptainer) | pass | 5 min, 4.9 GB → 4.5 GB `.sif` |
| `download --what index` (`NRG_3_hg38+hg38_HGDP1kGP`, the new default) | pass | 18 min, ~87 GB |
| `download --what genome --source ucsc` (pig, `susScr11`) | pass | 9 min, 3.0 GB |
| `download --what pams` | pass | seconds |
| `scorer-env check` (CRISPR-Bulge ML scorer) | pass, compute self-test OK | seconds |
| `complete-test` smoke test, genome-wide, variant index | pass | 14 min |
| `complete-search`, genome-wide variant-aware, population-level | pass | 59 min |
| `complete-search`, same guide with `--per-sample` | pass | 61 min |
| `generate-personal-card` for one individual | pass | 18 s |
| `complete-test` (benchmark mode) + `validate-test` | 2 benchmarks passed, 0 failed | 21 min + 6 s |
| `build-index-only` on a non-human genome (pig), then search | pass | 12 min + 21 min |
| SaCas9 index from the published kit, then variant-aware search | pass | 8 min + 33 min |
| `analyze_results.py` on every run above | pass | 3 s, 16 MB RAM on genome-wide output |

Not exercised, and so not claimed:

- **`download --what all`** — the test directory's hg38 reference data, reference index and
  annotations were hardlinked from an existing local CRISPRme checkout to save the download. The
  `--what index`, `--what genome` and `--what pams` modes were exercised; `--what all` and
  `--what assembly` were not.
- **`assembly-search`** — documented from v2.7.9's source and verified against the output of an
  earlier real run (v2.6.2, HPRC HG01255), but not re-executed on v2.7.9. It needs two
  genome-scale index builds and searches.
- **GPU scoring** (`--compute-backend cuda`) — the skill's wrapper does not pass a GPU into the
  container, so this path is CPU-only here.

### Behaviour worth knowing about

Found while testing v2.7.9. Each is handled in `SKILL.md`; several are places where upstream's
documentation and its code disagree, and are candidates for upstream issues.

- **`complete-test` can report success without testing anything.** With no index downloaded it
  prints download instructions and exits 0. With an index present it tests whichever index sorts
  first alphabetically, so a custom-PAM index (`NGG_…`, `NNGRRT_…`) is picked over the default
  `NRG_…` one and the run then fails pre-flight on guide length.
- **`complete-test` ignores `--chrom`** in its default smoke mode, despite the README, so it is
  always genome-wide and needs the full ~64 GB on a variant index.
- **`validate-test` only works on output from the legacy on-demand-build test mode**
  (`CRISPRME_ALLOW_ONDEMAND_BUILD=1`), not from the default smoke test. The `--vcf_dataset` flag
  the docs point at does not switch modes.
- **`generate-personal-card` accepts an unknown sample ID silently** — it writes an empty table
  and exits 0, which is indistinguishable from "this person has no private off-targets". It also
  matches sample IDs by substring.
- **`download --what index` appends to a shared `list_vcf.txt`.** With two variant indexes
  installed, a search given `--vcf list_vcf.txt` silently searches both panels.
- **`NRG_3_hg38+hg38_1000G2021_HGDP`**, the default index before 2.7, was deleted from
  HuggingFace in 2.7.8. Older notes and scripts pointing at it now fail.
- **Population-level per-person counts are worst-case upper bounds**, measured at roughly 1.5×
  the `--per-sample` numbers for the same guide. Only `--per-sample` resolves which individuals
  actually carry a site.
- **Non-SpCas9 nucleases get no CFD or CRISPR-Bulge score** — both models are SpCas9-trained — so
  those runs are ranked by edit distance alone. A missing score is not a low score.
- **The guide-length pre-flight error suggests the wrong fix.** It advises appending `N`s when the
  spacer itself is the wrong length for the PAM file.
- **`download --what pams` ships only three PAM files** (NGG, NRG, NNN); any other nuclease needs
  a hand-written PAM file.
- Deep searches are genuinely dangerous to launch blind: upstream's own estimator rates
  6 mismatches + 2 + 2 bulges as `EXTREME` (~200 GB of intermediates, OOM risk).

---

## Example

[`examples/flagship-search/`](examples/flagship-search/) holds real, unedited output from a
genome-wide variant-aware search — produced by a fresh Claude Code session given a single
one-line request, not by a hand-assembled command. Searching 4,091 people's genomes at the
version's recommended depth, it found 205,415 off-target sites, of which **97,879 (48%) do not
exist in the reference genome** and are only visible because the search covers population
variation, plus a lone perfect match in `BCL11A` — which CRISPRme treats as the presumed
on-target, since it cannot know the intended site — and a 101-site recommended validation panel.

The directory ships CRISPRme's own run manifest and parameters, that validation panel, the
per-guide summary table, and the skill's plain-language summary. Its README has the full
provenance, the exact command, and what each number means.

## Documentation

- **[`SKILL.md`](SKILL.md)** — the operational document Claude follows. It is also the most
  complete written account of how to run CRISPRme+ v2.7.9 on a shared server.
- **Upstream**: [`pinellolab/crisprme-plus`](https://github.com/pinellolab/crisprme-plus) —
  `README.md`, `METHODS.md`, `docs/PRECOMPUTED_INDEXES.md`, `docs/DATA_LAYOUT.md`,
  `docs/INPUT_FORMATS.md`. The skill defers to these for the science and the file formats; it
  does not duplicate them.

## Keeping up with upstream

CRISPRme+ releases frequently — sometimes several times a week — and 2.7.x has already changed
default search depth, the default variant panel, and the ML scorer. The skill pins a version and
says so: if `scripts/crisprme_cmd.sh --version` reports anything other than v2.7.9, confirm flags
with `<subcommand> --help` and check upstream's `CHANGELOG.md` before relying on this document.

## Citing CRISPRme

This skill is a thin operational layer. The tool, the methods, and the data are CRISPRme's — cite
the CRISPRme paper and CRISPRme+ as directed by
[upstream](https://github.com/pinellolab/crisprme-plus#4-citation).

CRISPRme+ itself is licensed under the MGB Open Access License 1.0: free for non-commercial
academic use, with commercial use requiring a separate licence.
