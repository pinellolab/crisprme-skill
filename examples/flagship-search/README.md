# Example: genome-wide variant-aware search

Real, unedited output from one CRISPRme+ v2.8.1 run. Nothing here was written by hand.

## Where it came from

The command below is the one a **fresh Claude Code session** produced when it was given a single
request that named neither the skill nor any CRISPRme command:

> I want to check guide CTAACAGTTGCTTTTATCAC for off-targets in human. Can you help?

From that, the session found and read the skill, checked the runtime and the machine's memory and
disk, asked which variant panel to use, padded the guide to match the PAM, verified the two
lengths agreed, and launched the search as a background job:

```
crisprme.py complete-search \
  --genome Genomes/hg38 --pam PAMs/20bp-NRG-SpCas9.txt \
  --guide guides/guide_CTAACAGT.txt \
  --vcf list_vcf.txt --samplesID list_samplesID.txt \
  --annotation Annotations/dhs+encode_screenv4+gencode+cosmic.hg38.bed.gz \
  --gene_annotation Annotations/gencode.protein_coding.bed.gz \
  --mm 4 --bDNA 1 --bRNA 1 --output CTAACAGT-HGDP1kGP-281 --thread 16
```

That cold-session test was done on v2.7.9. **The numbers and files in this folder come from
re-running the same command on v2.8.1**, in a normal working session rather than a cold one —
v2.8.1 fixed two indel bugs that change results, so the older figures are not reproducible and
have been dropped rather than carried forward.

The guide is CRISPRme's own example guide (sg1617). Its single perfect genomic match falls in
`BCL11A`.

**Run:** 2026-11-11, shared Linux server (88 cores, 1 TB RAM), published
`pinellolab/crisprme:v2.8.1` image under Apptainer. **2 h 18 m** on 16 threads — 19.5 min
reference search, 92 min variant search, the rest post-analysis and reporting. The run folder came
to 1.5 GB, of which the shareable `report.zip` is **3.9 MB** (17 files; the zip has been slim by
default since 2.7.10, which is what makes it shareable at all). Other heavy jobs were running on
the same server, so treat the wall time as an upper bound.

## Parameters

hg38, SpCas9 with the NRG PAM (NGG + NAG), up to 4 mismatches plus 1 DNA and 1 RNA bulge within a
6-edit budget — the version's recommended defaults. Variant-aware against
`NRG_3_hg38+hg38_HGDP1kGP`: HGDP plus 1000 Genomes, **4,091 people**, jointly re-phased,
125,180,264 variant records including 17,192,381 indels. Both bundled annotation files. COSMIC
excluded, which is the licence-safe default.

**Per-sample analysis, selected automatically.** No mode flag was passed. Since 2.8.0 CRISPRme
reads the index and picks the mode itself: this index is genotyped *and* phased, so it ran
per-sample — CONFIRMED cis phasing, named carrier samples, exact joint allele frequencies. The
resolved mode is recorded in `Results/<output>/.search_mode`, which is the only place it appears
(the manifest carries no `search_mode` key). On 2.7.9 and earlier the same command would have run
population-level, so this is the single biggest behavioural difference between this example and
the previous one.

## What it found

| | |
|---|---|
| Off-target sites | **170,659** |
| Created by a population variant, absent from the reference genome | **63,123 (37%)** |
| Where a variant creates a new PAM site | 6,087 |
| Perfect (0-mismatch, 0-bulge) matches | **1** — a lone perfect match, so no ambiguity about which site is the presumed on-target |
| Recommended validation panel | 101 sites (53 reference, 48 variant-created) |
| Need a SNP and an indel together | 363 (all **CONFIRMED** on one chromosome copy) |
| Need two SNPs together | 11,968 (11,754 **CONFIRMED**, 214 PUTATIVE) |

**More than a third of the predicted off-target sites do not exist in the reference genome**, and
they make up nearly half the validation panel. They are only visible because the search covers
population variation, which is the reason CRISPRme exists.

Because this run was per-sample, the co-occurrence rows are mostly *proven*: 11,754 of the 11,968
two-SNP sites are backed by phasing showing both variants on one chromosome copy in a real
person. A population-level run reports far more such rows and can only call them PUTATIVE.

Two panel entries show what that means concretely. The highest-scoring off-target (CFD 0.947) is
created by a single `CPS1` variant and carried, in confirmed cis, by **111 people**. Near the top
of the panel is an exonic `KCNQ1` site (CFD 0.667) carried by **exactly one person** in the
panel — an off-target that exists in a single individual and is invisible to a reference-only
search.

## Files

| File | What it is |
|---|---|
| `analyze_results.out.txt` | the skill's plain-language summary (`scripts/analyze_results.py`) |
| `run_manifest.json` | CRISPRme's own machine-readable run record: counts, panel composition, versions |
| `Params.txt` | the exact search parameters CRISPRme recorded |
| `panel_top100.tsv` | the recommended validation panel — the table you would use to design a confirmation assay |
| `summary_by_guide.CFD.txt` | off-target counts per mismatch/bulge class — its `Variant` column counts sites whose best alignment came from the variant genome, so it does not match the headline count of sites absent from the reference |

Everything else a run produces — `report.html` with its risk card and embedded plots, the full
annotated results table, the per-tier TSVs — lives in the run's `report.zip`.

## Reproducing it

With a CRISPRme+ v2.8.1 install and the default variant index downloaded, ask Claude the question
at the top of this file — or run the command above directly. Expect the same counts: on v2.7.9 an
independent run of this guide with identical parameters, in a separate directory on 24 threads
instead of 16, produced identical counts and a byte-identical validation panel.
