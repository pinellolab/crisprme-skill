#!/usr/bin/env python3
"""Summarize a completed CRISPRme Results/<job_name>/ directory into a plain-language
off-target risk report.

Reads only small files: the pre-aggregated summaries CRISPRme writes per run (summary_by_guide,
summary_by_samples, PopulationDistribution) and, from the run's own <job>_report.zip (CRISPRme+
2.5+), the run manifest, the recommended validation panel and the SNP+indel / SNP+SNP
co-occurrence tables. Without a report zip (older runs) it falls back to a memory-bounded
streaming top-N scan of bestMerge.txt. It never loads the full (possibly multi-GB) results table.

Also handles `assembly-search`'s reconciled `<name>_combined/<name>_combined_hg38.tsv` (one row per
reconciled hg38 locus with an `origin` column) with an origin/top-N summary.

The full, shareable assessment is CRISPRme's own report.html inside <job>_report.zip; this script
is the quick terminal digest of it.
"""
import argparse
import csv
import glob
import heapq
import io
import json
import os
import sys
import zipfile

# summary-file suffix and bestMerge column prefix per ranking. "crista" only exists in runs from
# CRISPRme 2.5 and earlier (CRISPR-Bulge replaced CRISTA in 2.6).
METHOD_SUMMARY_SUFFIX = {"cfd": "CFD", "crispr-bulge": "CRISPR-Bulge", "fewest": "fewest", "crista": "CRISTA"}
METHOD_COLUMN_PREFIX = {"cfd": "", "crispr-bulge": "CRISPR_BULGE_", "fewest": "MMBLG_", "crista": "CRISTA_"}
METHOD_LABEL = {"cfd": "CFD", "crispr-bulge": "CRISPR-Bulge", "fewest": "fewest mismatches+bulges", "crista": "CRISTA"}

csv.field_size_limit(sys.maxsize)


def find_guides(results_dir, job_name):
    pattern = os.path.join(results_dir, f"{job_name}.summary_by_guide.*.txt")
    guides = set()
    for path in glob.glob(pattern):
        base = os.path.basename(path)
        middle = base[len(f"{job_name}.summary_by_guide."):-len(".txt")]
        for suffix in METHOD_SUMMARY_SUFFIX.values():
            if middle.endswith("_" + suffix):
                guides.add(middle[: -len(suffix) - 1])
                break
    return sorted(guides)


def read_summary_by_guide(path):
    rows = []
    total = 0
    with open(path) as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            total += int(row["Combined"])
            rows.append(row)
    return rows, total


def read_population_distribution(path):
    with open(path) as fh:
        lines = [l.rstrip("\n") for l in fh if l.strip()]
    pops = {}
    for line in lines[1:]:
        parts = line.split("\t")
        pop = parts[0]
        total = 0
        for bucket in parts[1:]:
            total += sum(int(x) for x in bucket.split(","))
        pops[pop] = total
    return pops


def read_summary_by_samples(path, top_n=5):
    with open(path) as fh:
        fh.readline()  # guide-name header line
        reader = csv.DictReader(fh, delimiter="\t")
        rows = list(reader)
    by_targets = sorted(rows, key=lambda r: int(r["Targets in Sample"]), reverse=True)
    return rows, by_targets[:top_n]


def stream_top_risk(path, score_col, top_n=10):
    """Memory-bounded top-N scan: O(top_n) memory regardless of file size."""
    heap = []
    tie = 0
    with open(path) as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            try:
                score = float(row.get(score_col, ""))
            except (TypeError, ValueError):
                continue
            tie += 1
            item = (score, tie, row)
            if len(heap) < top_n:
                heapq.heappush(heap, item)
            elif score > heap[0][0]:
                heapq.heapreplace(heap, item)
    return sorted(heap, key=lambda x: x[0], reverse=True)


class ReportZip:
    """Read-only access to the small data files inside CRISPRme's <job>_report.zip."""

    def __init__(self, path):
        self.path = path
        self.zf = zipfile.ZipFile(path)
        self.names = set(self.zf.namelist())

    def has(self, member):
        return member in self.names

    def text(self, member):
        return self.zf.read(member).decode("utf-8", errors="replace")

    def tsv(self, member):
        return list(csv.DictReader(io.StringIO(self.text(member)), delimiter="\t"))

    def count_column(self, member, candidates):
        """Streams a (possibly very large) TSV member, counting values of the first matching
        column -- the SNP+SNP co-occurrence table alone can be hundreds of MB."""
        counts, total = {}, 0
        with self.zf.open(member) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"), delimiter="\t")
            header = next(reader, None)
            if header is None:
                return counts, 0
            header = [h.lstrip("#") for h in header]
            idx = next((header.index(c) for c in candidates if c in header), None)
            for row in reader:
                total += 1
                key = row[idx] if idx is not None and idx < len(row) else "?"
                counts[key] = counts.get(key, 0) + 1
        return counts, total

    def manifest(self):
        if not self.has("data/run_manifest.json"):
            return {}
        try:
            return json.loads(self.text("data/run_manifest.json"))
        except ValueError:
            return {}

    def params(self):
        if not self.has("data/Params.txt"):
            return {}
        out = {}
        for line in self.text("data/Params.txt").splitlines():
            key, _, value = line.partition("\t")
            out[key] = value
        return out


def find_report_zip(results_dir, job_name):
    path = os.path.join(results_dir, f"{job_name}_report.zip")
    if os.path.isfile(path):
        return path
    found = sorted(glob.glob(os.path.join(results_dir, "*_report.zip")))
    return found[0] if found else None


def run_command_line(results_dir, report):
    """The crisprme.py command that produced this run (from Params.txt or .command_line.txt)."""
    if report is not None:
        cmd = report.params().get("input_command")
        if cmd:
            return cmd
    path = os.path.join(results_dir, ".command_line.txt")
    if os.path.isfile(path):
        with open(path) as fh:
            return fh.read().strip()
    return ""


def print_run_header(results_dir, job_name, report):
    manifest = report.manifest() if report is not None else {}
    cmd = run_command_line(results_dir, report)
    version = manifest.get("crisprme_version")
    if not version:
        vpath = os.path.join(results_dir, ".version.txt")
        if os.path.isfile(vpath):
            with open(vpath) as fh:
                version = fh.read().split()[-1]
    search = manifest.get("search") or {}
    db = (manifest.get("database") or {}).get("databases") or {}
    variant_aware = " --vcf " in f" {cmd} " or bool(db)
    if not variant_aware:
        mode = "reference-only (no variant panel)"
    elif "--per-sample" in cmd:
        mode = "variant-aware, --per-sample (named carriers, CONFIRMED cis phasing)"
    else:
        mode = ("variant-aware, population-level default (worst-case representative per site; "
                "per-person haplotypes not resolved)")
    print(f"CRISPRme version: {version or 'unknown'}")
    print(f"Analysis: {mode}")
    if db:
        panel = ", ".join(f"{name} ({n} people)" for name, n in db.items())
        print(f"Variant panel: {panel}")
    if search:
        print(
            f"Search depth: {search.get('mismatches', '?')} mismatches, {search.get('bulges_dna', '?')} DNA / "
            f"{search.get('bulges_rna', '?')} RNA bulges, max {search.get('max_total_edits', '?')} total edits"
        )
    if manifest.get("pam"):
        print(f"Nuclease/PAM: {manifest.get('nuclease', '?')} / {manifest['pam']}")
    print()
    return manifest, cmd


def print_perfect_match_check(manifest, guide_rows):
    """A guide with >1 perfect (0 mismatch, 0 bulge) genomic match has no unambiguous on-target."""
    n_perfect = (manifest.get("counts") or {}).get("on_target_perfect_matches")
    if n_perfect is None and guide_rows is not None:
        n_perfect = sum(int(r["Combined"]) for r in guide_rows
                        if int(r["Mismatches"]) == 0 and int(r["Bulge Size"]) == 0)
    if n_perfect is None:
        return
    if n_perfect > 1:
        print(f"!! WARNING: {n_perfect} perfect (0-mismatch, 0-bulge) matches -- there is NO unambiguous on-target.")
        print("   Every perfect-match site is a candidate on-target; consider a different guide.\n")
    elif n_perfect == 1:
        print("On-target: exactly one perfect match (the presumed on-target site).\n")
    else:
        print("Note: no perfect match found (a variant-only or edited on-target, or a guide/genome mismatch).\n")


def print_cooccurrence(report):
    printed = False
    for member, label in (("data/indel_snp_cooc.tsv", "SNP+indel"), ("data/snp_snp_cooc.tsv", "SNP+SNP")):
        if not report.has(member):
            continue
        printed = True
        phases, total = report.count_column(member, ("phase", "Phase"))
        detail = f" ({', '.join(f'{k} {v}' for k, v in sorted(phases.items()))})" if total else ""
        print(f"{label} co-occurrence off-targets (need two variants together): {total}{detail}")
    if not printed:
        return
    print("  (CONFIRMED = phasing proves both variants sit on one chromosome copy in a real person;"
          " PUTATIVE = possible but unproven -- population-level runs report every SNP+SNP case as"
          " PUTATIVE; --per-sample resolves them)\n")


def print_panel(report, top_n):
    rows = report.tsv("data/panel_top100.tsv")
    if rows and all(r.get("CFD", "-") in ("-", "") for r in rows):
        print("Note: no CFD / CRISPR-Bulge scores -- both are trained on SpCas9, so for this nuclease the"
              " panel is ranked by mismatches+bulges (edit distance) only.")
    print(f"Recommended validation panel: {len(rows)} sites (data/panel_top100.tsv in the report zip). Top {min(top_n, len(rows))}:")
    for r in rows[:top_n]:
        gene = r.get("Gene", "-")
        region = r.get("Gene_region", "-")
        where = f"{gene}/{region}" if gene not in ("-", "") else region
        flags = []
        if r.get("Perfect_match") == "Yes":
            flags.append("PERFECT MATCH")
        if r.get("REF/ALT_origin") == "ALT":
            variants = r.get("Variant", "?").split(",")
            more = f" (+{len(variants) - 2} more)" if len(variants) > 2 else ""
            flags.append(f"variant {','.join(variants[:2])}{more}")
        if r.get("IntOGen_cancer_driver", "-") not in ("-", ""):
            flags.append("cancer-driver gene")
        flag_text = f"  [{'; '.join(flags)}]" if flags else ""
        scores = "  ".join(f"{col}={r[col]}" for col in ("CFD", "CRISPR-Bulge") if r.get(col, "-") not in ("-", ""))
        print(
            f"  {r.get('rank', '?'):>3}. {r['Chromosome']}:{r['Position']}({r.get('Strand', '?')})  "
            f"{r.get('Mismatches', '?')}mm+{r.get('Bulges', '?')}b  {scores or '(no SpCas9 score)'}  "
            f"Observed={r.get('Observed', '-')}  {where}{flag_text}"
        )
    regions = {}
    for r in rows:
        regions[r.get("Gene_region", "-")] = regions.get(r.get("Gene_region", "-"), 0) + 1
    if any(k not in ("-", "") for k in regions):
        print("  Panel sites by gene region: " + ", ".join(f"{k} {v}" for k, v in sorted(regions.items(), key=lambda kv: -kv[1])))
    print()


ASSEMBLY_SEARCH_HAPLOTYPES = ("paternal", "maternal")
ORIGIN_MEANING = {
    "both": "found on both haplotypes (homozygous-equivalent)",
    "paternal_only": "paternal haplotype only (heterozygous-equivalent)",
    "maternal_only": "maternal haplotype only (heterozygous-equivalent)",
    "both_haplotype_private": "no hg38 equivalent, but the same site on both haplotypes (invisible to reference-based search)",
}


def find_combined_tsv(results_dir, job_name):
    """Returns the path to an assembly-search combined report if this results_dir is one.

    `crisprme.py assembly_search()` names it `<output_base>_combined_hg38.tsv` inside
    `Results/<output_base>_combined/` — and `job_name` (the results dir's basename) is already
    `<output_base>_combined`, so the file is always `<job_name>_hg38.tsv`.
    """
    path = os.path.join(results_dir, f"{job_name}_hg38.tsv")
    return path if os.path.isfile(path) else None


def summarize_combined_report(results_dir, path, top_n=10):
    """Summary of an assembly-search combined hg38 report: origin counts + top-N by best CFD."""
    with open(path) as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))

    print(f"Total reconciled off-target loci: {len(rows)}")
    origin_counts = {}
    for r in rows:
        origin_counts[r.get("origin", "?")] = origin_counts.get(r.get("origin", "?"), 0) + 1
    print("By origin:")
    for origin, count in sorted(origin_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {origin}: {count}  -- {ORIGIN_MEANING.get(origin, '')}")
    print(
        "  (each haplotype's remaining non-mappable count -- sites with no hg38 equivalent at all -- "
        "is printed at the end of the assembly-search run's log)"
    )

    scored = []
    for r in rows:
        best_score, best_hap = None, None
        for hap in ASSEMBLY_SEARCH_HAPLOTYPES:
            val = r.get(f"CFD_score_(fewest_mm+b)_{hap}")
            try:
                fv = float(val)
            except (TypeError, ValueError):
                continue
            if best_score is None or fv > best_score:
                best_score, best_hap = fv, hap
        if best_score is not None:
            scored.append((best_score, best_hap, r))
    scored.sort(key=lambda x: -x[0])

    top_rows = scored[:top_n]
    print(f"\nTop {len(top_rows)} highest-CFD reconciled sites:")
    for score, hap, r in top_rows:
        chrom = r.get("hg38_chr") or "no-hg38"
        pos = r.get("hg38_start") or "-"
        if pos.endswith(".0"):
            pos = pos[:-2]
        gene = r.get("Annotation_closest_gene_name") or ""
        region = r.get("Annotation_gene_region") or ""
        context = f"  {gene}/{region}".rstrip("/") if (gene or region) else ""
        print(f"  {chrom}:{pos}  CFD={score:.3f}  origin={r.get('origin', '?')}  (best haplotype: {hap}){context}")

    combined_zip = find_report_zip(results_dir, os.path.basename(results_dir))
    if combined_zip:
        print(f"\nFull combined report (both haplotypes' reports inside): {combined_zip} -> unzip, open report.html")


def read_guide_severity(results_dir, job_name, guide, suffix):
    """Per-guide totals from its summary_by_guide file, for ranking guides against each other."""
    path = os.path.join(results_dir, f"{job_name}.summary_by_guide.{guide}_{suffix}.txt")
    if not os.path.isfile(path):
        return None
    rows, total = read_summary_by_guide(path)
    variant_total = sum(int(r["Variant"]) for r in rows)
    # near-exact matches (<=2 mismatches, any bulge) are the strongest proxy for real off-target
    # activity already present in this per-guide breakdown
    low_mm_total = sum(int(r["Combined"]) for r in rows if int(r["Mismatches"]) <= 2)
    return {"total": total, "variant_total": variant_total, "low_mm_total": low_mm_total}


def print_guide_comparison(results_dir, job_name, guides, suffix, method_label):
    """Ranks every guide in a multi-guide run by apparent off-target severity (a quick proxy)."""
    stats = {g: s for g in guides if (s := read_guide_severity(results_dir, job_name, g, suffix)) is not None}
    if len(stats) < 2:
        return
    print(f"=== Guide comparison ({len(stats)} guides, {method_label} ranking) ===")
    ranked = sorted(stats.items(), key=lambda kv: (kv[1]["low_mm_total"], kv[1]["total"]))
    print(f"{'Guide':<28} {'Total off-targets':>18} {'0-2mm off-targets':>18} {'Variant-only':>13}")
    for g, s in ranked:
        print(f"{g:<28} {s['total']:>18} {s['low_mm_total']:>18} {s['variant_total']:>13}")
    best = ranked[0][0]
    print(
        f"\nLowest apparent risk: {best} (fewest near-exact [0-2 mismatch] predicted off-targets --"
        " generally the strongest signal for real off-target activity). This is a quick ranking"
        " from already-computed counts, not a formal specificity score: it doesn't weigh"
        " individual CFD/CRISPR-Bulge scores or genomic context (promoters, coding exons) of specific"
        " sites -- treat it as a starting point and check each guide's report.html.\n"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results_dir", help="Path to a completed CRISPRme Results/<name>/ directory")
    ap.add_argument("--guide", help="Guide sequence to summarize (required if the run searched multiple guides)")
    ap.add_argument("--method", choices=["cfd", "crispr-bulge", "fewest", "crista"], default="cfd",
                    help="Which of CRISPRme's rankings the summary counts use (default: cfd; "
                         "crista only for runs from CRISPRme 2.5 and earlier)")
    ap.add_argument("--top", type=int, default=10, help="Number of highest-risk sites to list (default: 10)")
    args = ap.parse_args()

    results_dir = args.results_dir.rstrip("/")
    job_name = os.path.basename(results_dir)
    if not os.path.isdir(results_dir):
        sys.exit(f"Not a directory: {results_dir}")

    combined_tsv = find_combined_tsv(results_dir, job_name)
    if combined_tsv:
        print(f"=== CRISPRme assembly-search combined results: {job_name} ===\n")
        summarize_combined_report(results_dir, combined_tsv, top_n=args.top)
        return

    guides = find_guides(results_dir, job_name)
    if not guides:
        sys.exit(
            f"No summary_by_guide files found under {results_dir} — is this a completed "
            "complete-search/complete-test Results dir?"
        )

    suffix = METHOD_SUMMARY_SUFFIX[args.method]
    prefix = METHOD_COLUMN_PREFIX[args.method]
    label = METHOD_LABEL[args.method]
    if not glob.glob(os.path.join(results_dir, f"{job_name}.summary_by_guide.*_{suffix}.txt")):
        available = sorted({os.path.basename(p).rsplit("_", 1)[-1][:-4]
                            for p in glob.glob(os.path.join(results_dir, f"{job_name}.summary_by_guide.*.txt"))})
        sys.exit(f"This run has no '{suffix}' summaries (it has: {', '.join(available)}). "
                 "CRISTA exists only in runs from CRISPRme 2.5 and earlier; CRISPR-Bulge only in 2.6+.")

    zip_path = find_report_zip(results_dir, job_name)
    report = ReportZip(zip_path) if zip_path else None

    if len(guides) > 1:
        print_guide_comparison(results_dir, job_name, guides, suffix, label)

    guide = args.guide or (guides[0] if len(guides) == 1 else None)
    if guide is None:
        sys.exit("Pick one guide for a full breakdown with --guide:\n  " + "\n  ".join(guides))
    if guide not in guides:
        sys.exit(f"Guide '{guide}' not found in this run. Available: {', '.join(guides)}")

    summary_guide_path = os.path.join(results_dir, f"{job_name}.summary_by_guide.{guide}_{suffix}.txt")
    pop_dist_path = os.path.join(results_dir, f".{job_name}.PopulationDistribution_{suffix}.txt")
    summary_samples_path = os.path.join(results_dir, f"{job_name}.summary_by_samples.{guide}_{suffix}.txt")
    best_merge_path = os.path.join(results_dir, f"{job_name}.bestMerge.txt")

    print(f"=== CRISPRme results summary: {job_name} ===")
    print(f"Guide: {guide}   Counts ranked by: {label}")
    manifest, cmd = print_run_header(results_dir, job_name, report)
    per_sample = "--per-sample" in cmd
    variant_aware = " --vcf " in f" {cmd} "
    if len(guides) > 1:
        manifest = {}  # the manifest's counts are run-wide; use this guide's own summary instead

    guide_rows = None
    if os.path.isfile(summary_guide_path):
        guide_rows, total = read_summary_by_guide(summary_guide_path)
        variant_only = sum(int(r["Variant"]) for r in guide_rows)
        pam_created = sum(int(r["PAM Creation"]) for r in guide_rows)
        print(f"Total off-target sites: {total}")
        if variant_aware:
            print(f"  found only because of a population variant (absent from the reference genome): {variant_only}")
            print(f"  where a variant creates a brand-new PAM site: {pam_created}")
        print("Breakdown by mismatch/bulge count:")
        for r in sorted(guide_rows, key=lambda r: (int(r["Mismatches"]), int(r["Bulge Size"]))):
            btype = "no bulge" if r["Bulge Type"] == "X" else f"{r['Bulge Type']} bulge"
            variant_note = f" ({r['Variant']} variant-only)" if variant_aware else ""
            print(f"  {r['Mismatches']} mismatch(es), bulge size {r['Bulge Size']} ({btype}): {r['Combined']} sites{variant_note}")
    else:
        print(f"[missing] {summary_guide_path}")
    print()

    print_perfect_match_check(manifest, guide_rows)

    if os.path.isfile(pop_dist_path):
        pops = read_population_distribution(pop_dist_path)
        if any(v for k, v in pops.items() if k != "REF"):
            print("Off-target site totals by population (REF = reference genome, no variant needed):")
            if not per_sample:
                print("  (population-level run: these are worst-case upper bounds -- typically ~1.5x the"
                      " --per-sample counts)")
            for pop, total in sorted(pops.items(), key=lambda kv: -kv[1]):
                print(f"  {pop}: {total}")
            print()

    if report is not None:
        print_cooccurrence(report)

    if os.path.isfile(summary_samples_path) and per_sample:
        all_rows, top_samples = read_summary_by_samples(summary_samples_path)
        if all_rows:
            print(f"Samples with the most individual off-target sites (of {len(all_rows)} samples in this run):")
            for r in top_samples:
                print(f"  {r['Sample']} ({r['Population']}/{r['Super Population']}): {r['Targets in Sample']} targets")
            print()
    elif variant_aware and not per_sample:
        print("Per-person carrier counts: not available -- this was a population-level run. Re-run with "
              "--per-sample (genotyped index) to get named carriers.\n")

    if report is not None and report.has("data/panel_top100.tsv"):
        print_panel(report, args.top)
        print(f"Full report: {zip_path} -> unzip, open report.html (shareable, works offline)")
    elif os.path.isfile(best_merge_path):
        score_col = f"{prefix}CFD"
        top_rows = stream_top_risk(best_merge_path, score_col, top_n=args.top)
        print(f"Top {len(top_rows)} highest-{label}-score off-target sites (no report zip found; from bestMerge.txt):")
        for score, _, row in top_rows:
            chrom = row.get(f"{prefix}Chromosome", "?")
            pos = row.get(f"{prefix}Position", "?")
            mm = row.get(f"{prefix}Mismatches", "?")
            bulge = row.get(f"{prefix}Bulge_Size", "?")
            ann = row.get(f"{prefix}Annotation_Type", "NA") or "NA"
            rsid = row.get(f"{prefix}rsID", "NA")
            variant_flag = f", variant {rsid}" if rsid not in ("NA", "", None) else ""
            print(f"  {chrom}:{pos}  score={score:.3f}  {mm}mm+{bulge}bulge  annotation={ann}{variant_flag}")
        print("Regenerate the shareable report with: crisprme.py generate-report --result-dir " + results_dir)
    else:
        print(f"[missing] {best_merge_path} and no report zip")


if __name__ == "__main__":
    main()
