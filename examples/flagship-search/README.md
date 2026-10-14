# Example: genome-wide variant-aware search

Real, unedited output from one CRISPRme+ v2.7.9 run. Nothing here was written by hand.

## Where it came from

A **fresh Claude Code session** (v2.1.296) was started in a directory containing only this skill
and a standard CRISPRme+ install — reference genome, the default variant index, annotations, PAM
files. It was given one request, which did not name the skill or any CRISPRme command:

> I want to check guide CTAACAGTTGCTTTTATCAC for off-targets in human. Can you help?

From that, the session found and read the skill, checked the runtime and the machine's memory and
disk, asked which variant panel to use and whether per-person resolution was needed, padded the
guide to match the PAM, verified the two lengths agreed, and launched the search as a background
job. The command it produced:

```
crisprme.py complete-search \
  --genome Genomes/hg38 --pam PAMs/20bp-NRG-SpCas9.txt \
  --guide guides/guide_CTAACAGT.txt \
  --vcf list_vcf.txt --samplesID list_samplesID.txt \
  --annotation Annotations/dhs+encode_screenv4+gencode+cosmic.hg38.bed.gz \
  --gene_annotation Annotations/gencode.protein_coding.bed.gz \
  --mm 4 --bDNA 1 --bRNA 1 --output CTAACAGT-HGDP1kGP-1014 --thread 16
```

The guide is CRISPRme's own example guide (sg1617). Its single perfect genomic match falls in
`BCL11A`.

**Run:** 2026-10-14, shared Linux server (88 cores, 1 TB RAM), published
`pinellolab/crisprme:v2.7.9` image under Apptainer. **80 minutes** on 16 threads. The run folder
came to 3.8 GB, of which the shareable `report.zip` is 195 MB (20 files).

## Parameters

hg38, SpCas9 with the NRG PAM (NGG + NAG), up to 4 mismatches plus 1 DNA and 1 RNA bulge within a
6-edit budget — the version's recommended defaults. Variant-aware against
`NRG_3_hg38+hg38_HGDP1kGP`: HGDP plus 1000 Genomes, **4,091 people**, jointly re-phased,
125,180,264 variant records including 17,192,381 indels. Population-level analysis (the default).
Both bundled annotation files. COSMIC excluded, which is the licence-safe default.

## What it found

| | |
|---|---|
| Off-target sites | **205,415** |
| Created by a population variant, absent from the reference genome | **97,879 (48%)** |
| Where a variant creates a new PAM site | 10,837 |
| Perfect (0-mismatch, 0-bulge) matches | **1** — a lone perfect match, so no ambiguity about which site is the presumed on-target |
| Recommended validation panel | 101 sites |
| Need a SNP and an indel together | 642 (632 confirmed on one chromosome copy) |
| Need two SNPs together | 342,396 (all unconfirmed at population level) |

**Nearly half of the predicted off-target sites do not exist in the reference genome.** They are
only visible because the search covers population variation, which is the reason CRISPRme exists.

Two entries in the validation panel show what that means concretely. The highest-scoring
off-target (CFD 0.947) is created by a single variant in `CPS1` carried by 111 people in the
panel. Another is a **0-mismatch, 2-bulge** site created by a three-base deletion and carried by
one person — a perfect-match-quality off-target that exists in a single individual and would be
invisible to a reference-only search.

## Files

| File | What it is |
|---|---|
| `analyze_results.out.txt` | the skill's plain-language summary (`scripts/analyze_results.py`) |
| `run_manifest.json` | CRISPRme's own machine-readable run record: counts, panel composition, versions |
| `Params.txt` | the exact search parameters CRISPRme recorded |
| `panel_top100.tsv` | the recommended validation panel — the table you would use to design a confirmation assay |
| `summary_by_guide.CFD.txt` | off-target counts per mismatch/bulge class — its `Variant` column counts sites whose best alignment came from the variant genome, so it is larger than the headline count of sites absent from the reference |

Everything else a run produces — `report.html` with embedded plots, the full annotated results
table, the per-tier TSVs — is too large to ship here. Those live in the run's `report.zip`.

## Reproducing it

With a CRISPRme+ v2.7.9 install and the default variant index downloaded, ask Claude the question
at the top of this file — or run the command above directly.

An independent run of the same guide with identical parameters, in a separate directory on 24
threads instead of 16, produced **identical counts and a byte-identical validation panel**.
