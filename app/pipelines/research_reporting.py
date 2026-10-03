"""Evidence selection, quality assessment, bounded synthesis and report rendering."""

import re
from collections import Counter

from app.models.research import ResearchOutcome

RESEARCH_ARTIFACTS = (
    "pages.json", "passages.json", "evidence.json", "rejected_evidence.json",
    "synthesis.json", "research_report.md", "research_quality.json",
    "research_diagnostics.json", "research_events.jsonl", "research_limited_overview.md",
)
NUMERIC_CATEGORIES = {
    "sample_size", "denominator", "percentage", "test_statistic", "p_value",
    "confidence_interval", "effect_size", "diagnostic_accuracy",
}
NUMBER_TOKEN = re.compile(r"(?<![A-Za-z0-9])(?:\d[\d,]*(?:\.\d+)?|\.\d+)%?(?!\d)")


def _unsupported_figures(claim, evidence):
    """Figures in prose must occur literally in a numeric record cited by this claim."""
    allowed = {
        match.group() for evidence_id in claim.evidence_ids
        if evidence_id in evidence and evidence[evidence_id]["category"] in NUMERIC_CATEGORIES
        for match in NUMBER_TOKEN.finditer(evidence[evidence_id]["value"])
    }
    return {match.group() for match in NUMBER_TOKEN.finditer(claim.text)} - allowed


def select_evidence(records, document_type, limit=9):
    """Reserve bounded report space for aim, method, main results and caveats."""
    candidates = [e for e in records if e.origin == "current_study" or
                  (document_type == "review" and e.origin == "cited_study")]
    section_score = {"abstract": 9, "results": 8, "conclusions": 6, "limitations": 7,
                     "methods": 5, "discussion": 4, "introduction": 3, "front_matter": 0}

    def rank(e):
        return (section_score.get(e.section, 1) + (2 if e.importance == "primary" else 0),
                e.origin == "current_study", e.source_kind == "text", -len(e.quote), -e.page)

    ranked = sorted(candidates, key=rank, reverse=True)
    selected, used, per_page, per_passage = [], set(), Counter(), Counter()

    def add(record):
        key = (record.origin, record.attribution, record.category, record.value)
        if key in used or len(selected) >= limit or per_passage[record.passage_id] >= 2:
            return
        used.add(key)
        selected.append(record)
        per_page[record.page] += 1
        per_passage[record.passage_id] += 1

    for categories in (("objective",), ("study_design",),
                       ("sample_size", "denominator", "population"),
                       ("finding", "percentage", "effect_size", "test_statistic",
                        "p_value", "confidence_interval", "diagnostic_accuracy"),
                       ("test_statistic", "effect_size", "confidence_interval"),
                       ("p_value",),
                       ("conclusion",), ("limitation",)):
        candidate = next((e for e in ranked if e.category in categories), None)
        if candidate:
            add(candidate)
    for record in ranked:
        if record.category != "metadata" and per_page[record.page] < 3:
            add(record)
    return selected


def assess_coverage(records, selected, document_type, *, extraction_complete,
                    problems, rejected_attempts, eligible_passages, pages,
                    processing_error=None):
    own = [e for e in records if e.origin == "current_study"]
    coverage = {
        "objective": any(e.category == "objective" for e in own),
        "methods": any(e.category == "study_design" for e in own),
        "population": any(e.category in {"population", "sample_size", "denominator"} for e in own),
        "findings": any(e.category in {"finding", *NUMERIC_CATEGORIES} for e in own),
        "conclusions": any(e.category == "conclusion" for e in own),
        "limitations": any(e.category == "limitation" for e in own),
        "cited_findings": any(e.origin == "cited_study" for e in records),
        "central_findings": any(
            e.origin == "current_study"
            and e.section in {"abstract", "results", "discussion", "conclusions"}
            and e.category in {"finding", *NUMERIC_CATEGORIES, "conclusion"}
            for e in records
        ),
    }
    applicable = {
        "empirical": {"objective", "methods", "findings", "conclusions", "limitations",
                      "population", "sample_size", "denominator", "statistics"},
        "review": {"objective", "findings", "conclusions", "limitations", "statistics"},
        "theoretical": {"objective", "findings", "conclusions", "limitations"},
        "unknown": {"objective", "methods", "findings", "conclusions", "limitations",
                    "population", "sample_size", "denominator", "statistics"},
    }[document_type]
    observed = {
        "objective": coverage["objective"], "methods": coverage["methods"],
        "findings": coverage["findings"], "conclusions": coverage["conclusions"],
        "limitations": coverage["limitations"], "population": coverage["population"],
        "sample_size": any(e.category == "sample_size" for e in own),
        "denominator": any(e.category == "denominator" for e in own),
        "statistics": any(e.category in NUMERIC_CATEGORIES - {"sample_size", "denominator"} for e in own),
    }
    assessment = {}
    for name in ("objective", "methods", "findings", "conclusions", "limitations", "population",
                 "sample_size", "denominator", "statistics"):
        if name not in applicable:
            assessment[name] = "not_applicable"
        elif observed[name]:
            assessment[name] = "supported"
        elif not extraction_complete:
            assessment[name] = "not_extracted"
        else:
            # Absence from accepted evidence does not prove the paper omitted it.
            assessment[name] = "uncertain"

    missing = [name for name in ("objective", "findings") if not coverage[name]]
    if not processing_error:
        if not coverage["central_findings"]:
            missing.append("central_claims_not_adequately_attributed_in_principal_sections")
        results_pages = {p.page for p in eligible_passages if p.section == "results"
                         and (p.kind == "table" or len(p.text.split()) >= 10)}
        represented_pages = {e.page for e in records if e.origin != "background"}
        uncovered = sorted(results_pages - represented_pages)
        if uncovered:
            missing.append("results_pages_without_evidence: " + ", ".join(map(str, uncovered)))
        if document_type == "unknown":
            missing.append("document_type_unresolved")
        if not extraction_complete:
            missing.append("extraction_interrupted")

    source_issues = []
    relevant_pages = {p.page for p in eligible_passages}
    body_span = (min(relevant_pages), max(relevant_pages)) if relevant_pages else None
    for page in pages:
        if relevant_pages and page["page"] not in relevant_pages:
            if (body_span[0] <= page["page"] <= body_span[1]
                    and not page.get("normalized_text", "").strip()):
                source_issues.append(f"PDF page {page['page']} has no extractable text")
            continue
        source_issues.extend(f"PDF page {page['page']}: {warning}" for warning in page.get("warnings", []))
        if not page.get("normalized_text", "").strip():
            source_issues.append(f"PDF page {page['page']} has no extractable text")
    if any(any(w.startswith("Numeric token discrepancy") for w in p.get("warnings", []))
           for p in pages if not relevant_pages or p["page"] in relevant_pages):
        source_issues.append("Numeric extraction discrepancy requires manual page review")
    if any("Table" in " ".join(e.warnings) for e in records):
        source_issues.append("Table headers or footnote associations are provisional")

    reasons = [] if processing_error else list(problems)
    substantive = any(e.origin == "current_study" and
        e.category in {"finding", *NUMERIC_CATEGORIES, "conclusion"} for e in selected)
    if processing_error:
        status = "failed"
        reasons = ["Processing failed before a validated report could be completed"]
    elif not substantive or any(name in missing for name in ("objective", "findings")):
        status = "failed"
        reasons.append("Required attributable central evidence was not established")
    elif missing or problems or source_issues or document_type == "unknown":
        status = "partial"
    else:
        status = "completed"
    return ResearchOutcome(
        status=status, processing_status="failed" if processing_error else "completed",
        processing_error=processing_error, document_type=document_type, reasons=reasons,
        missing_coverage=missing, coverage=coverage, coverage_assessment=assessment,
        source_quality_issues=sorted(set(source_issues)), accepted_records=len(records),
        rejected_attempts=rejected_attempts, selected_records=len(selected),
        extraction_complete=extraction_complete,
    )


def escape(text):
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\*_\[\]#|])", r"\\\1", text)


def build_synthesis_payload(selected, passages, metadata, *, max_items=9, max_chars=7600):
    """Bound synthesis to validated records and their known page/table context."""
    by_id = {p.id: p for p in passages}
    payload, size, count = [], 0, 0
    for record in selected:
        if count >= max_items:
            break
        source_ids, context, unresolved = [record.passage_id], [], []
        for context_id in (getattr(record, "context_ids", None) or []):
            passage = by_id.get(context_id)
            if passage is None:
                unresolved.append(context_id)
                continue
            context.append({
                "id": passage.id, "page": passage.page, "section": passage.section,
                "kind": getattr(passage, "kind", "text"),
                "table_id": getattr(passage, "table_id", None), "text": passage.text[:500],
            })
            source_ids.append(passage.id)
        item = {
            "evidence_id": record.id, "passage_id": record.passage_id, "page": record.page,
            "section": record.section, "category": record.category, "origin": record.origin,
            "attribution": record.attribution, "importance": record.importance, "value": record.value,
            "source_text": record.quote, "source_ids": source_ids, "context": context,
            "unresolved_context_ids": unresolved,
            "context_status": "linked" if context else ("unresolved" if unresolved else "not_linked"),
        }
        cost = len(repr(item))
        if size + cost > max_chars:
            continue
        payload.append(item)
        size += cost
        count += 1
    safe_metadata = []
    for item in metadata:
        source = by_id.get(item.get("passage_id"))
        if source:
            safe_metadata.append({"field": item["field"], "value": item["value"],
                                  "source_id": source.id, "page": source.page})
    if safe_metadata and size < max_chars:
        payload.append({"bibliographic_metadata": safe_metadata})
    return payload


def validate_narrative(narrative, payload):
    evidence = {item["evidence_id"]: item for item in payload if "evidence_id" in item}
    source_ids = {source_id for item in evidence.values() for source_id in item["source_ids"]}
    errors, claims = [], []
    section_categories = {
        "introduction": {"objective", "study_design", "finding", "conclusion"},
        "methods_scope": {"study_design", "population", "sample_size", "denominator"},
        "key_findings": {"finding", *NUMERIC_CATEGORIES, "conclusion"},
        "statistical_information": NUMERIC_CATEGORIES,
        "conclusion": {"finding", "conclusion", "limitation", *NUMERIC_CATEGORIES},
    }
    for section in ("introduction", "methods_scope", "key_findings",
                    "statistical_information", "conclusion"):
        value = getattr(narrative, section)
        claims.extend((section, claim) for claim in (
            [value] if section == "introduction" and value else value or []))
    for section, claim in claims:
        if _unsupported_figures(claim, evidence):
            errors.append("Narrative figure is not an exact value in its cited numeric evidence")
        if claim is narrative.introduction:
            sentences = len(re.findall(r"[.!?](?:\s|$)", claim.text.strip())) or 1
            if len(claim.text) > 450 or sentences > 3:
                errors.append("Introduction must be one short, accessible paragraph")
        if not set(claim.evidence_ids) <= evidence.keys():
            errors.append("Narrative cites an evidence ID not supplied to synthesis")
            continue
        if not set(claim.source_ids) <= source_ids:
            errors.append("Narrative cites a source passage not supplied to synthesis")
            continue
        for evidence_id in claim.evidence_ids:
            if evidence[evidence_id]["category"] not in section_categories[section]:
                errors.append(f"Narrative uses an incompatible evidence category in {section}")
            cited_record = evidence[evidence_id]
            claim_categories = {evidence[item_id]["category"] for item_id in claim.evidence_ids}
            if ("p_value" in claim_categories and not claim_categories & {"finding", "effect_size"}
                    and re.search(r"\b(?:caus(?:e|es|ed|al)|strong(?:er)?|weak(?:er)?|large|small)\b",
                                  claim.text, re.I)):
                errors.append("A p-value alone cannot support a causal or association-strength claim")
            if not set(claim.source_ids) & set(evidence[evidence_id]["source_ids"]):
                errors.append(f"Narrative citation does not link to evidence {evidence_id}")
            item = evidence[evidence_id]
            if item.get("origin") == "cited_study":
                attribution = item.get("attribution") or ""
                if not ((attribution and attribution.casefold() in claim.text.casefold())
                        or re.search(r"\b(?:prior|previous|earlier|cited)\s+(?:study|research|work)\b",
                                     claim.text, re.I)):
                    errors.append(f"Cited-study claim lacks explicit attribution for {evidence_id}")
    if narrative.introduction is None:
        errors.append("Narrative introduction is missing")
    if not narrative.key_findings:
        errors.append("Narrative key findings are missing")
    key_finding_ids = {evidence_id for claim in narrative.key_findings
                       for evidence_id in claim.evidence_ids}
    primary_current_ids = {item["evidence_id"] for item in evidence.values()
        if item.get("origin") == "current_study" and item.get("importance") == "primary"
        and item.get("category") in {"finding", *NUMERIC_CATEGORIES, "conclusion"}}
    if primary_current_ids and not key_finding_ids & primary_current_ids:
        errors.append("Key findings omit the supplied primary current-study evidence")
    return sorted(set(errors))


def _cite_claim(claim, evidence_by_id, passages_by_id):
    refs = []
    for evidence_id in claim.evidence_ids:
        record = evidence_by_id[evidence_id]
        refs.append(f"{record.id}; {record.passage_id}; PDF p. {record.page}")
        for source_id in claim.source_ids:
            if source_id != record.passage_id and source_id in (getattr(record, "context_ids", None) or []):
                context = passages_by_id.get(source_id)
                if context:
                    refs.append(f"{source_id}; PDF p. {context.page}")
    return " [" + "; ".join(dict.fromkeys(refs)) + "]"


def _numeric_context(record, width=90):
    """Show only nearby source wording while keeping the exact measure visible."""
    start = max(0, record.value_start - width)
    end = min(len(record.quote), record.value_end + width)
    excerpt = record.quote[start:end].strip()
    return ("…" if start else "") + excerpt + ("…" if end < len(record.quote) else "")


def render_report(source, selected, passages, metadata, outcome, narrative=None):
    by_id = {p.id: p for p in passages}
    evidence_by_id = {e.id: e for e in selected}
    lines = ["# Research report", "", f"Source: {escape(source)}", ""]
    for field in ("title", "authors", "year", "journal", "doi"):
        item = next((m for m in metadata if m["field"] == field
                     and m.get("passage_id") in by_id), None)
        if item:
            passage = by_id[item["passage_id"]]
            lines.append(f"**{field.title()}:** {escape(item['value'])} "
                         f"[{passage.id}; PDF p. {passage.page}]")
    if metadata:
        lines.append("")
    quality = "Complete quality" if outcome.status == "completed" else f"{outcome.status.title()} quality"
    lines += [f"**Quality:** {quality}. Processing: {outcome.processing_status}.", ""]
    if outcome.source_quality_issues:
        lines += ["Source readability/structure needs review: " +
                  escape("; ".join(outcome.source_quality_issues[:3])) + ".", ""]
    sections = (
        ("Introduction / What this paper is about", "introduction", True),
        ("Methods and scope", "methods_scope", False), ("Key findings", "key_findings", False),
        ("Statistical information", "statistical_information", False), ("Conclusion", "conclusion", False),
    )
    for title, field, single in sections:
        lines += [f"## {title}", ""]
        if narrative is None:
            lines += ["A validated narrative could not be generated. See the limited overview and diagnostics.", ""]
            continue
        claims = getattr(narrative, field)
        claims = [claims] if single and claims else ([] if single else claims)
        stats = [e for e in selected if e.category in NUMERIC_CATEGORIES] \
                if field == "statistical_information" else []
        if not claims and not stats:
            lines += ["No supported material was extracted for this section.", ""]
            continue
        for claim in claims:
            lines += [escape(claim.text) + _cite_claim(claim, evidence_by_id, by_id), ""]
        if field == "statistical_information":
            for evidence in stats:
                label = evidence.category.replace("_", " ").title()
                attribution = (f"Cited study ({escape(evidence.attribution or 'attribution unclear')}) reported"
                               if evidence.origin == "cited_study" else "The paper reported")
                lines += [f"- **{attribution} {label}:** {escape(evidence.value)} — "
                          f"{escape(_numeric_context(evidence))} "
                          f"[{evidence.id}; {evidence.passage_id}; PDF p. {evidence.page}]", ""]
    if outcome.missing_coverage or outcome.status != "completed":
        lines += ["## Quality note", "",
            f"This report has **{outcome.status}** research quality. Review its coverage assessment and cited PDF passages before relying on it."]
        if outcome.missing_coverage:
            lines += ["", "Coverage to review: " + escape(", ".join(outcome.missing_coverage)) + "."]
    lines += ["", "Audit IDs resolve through passages.json and evidence.json. Raw text, coordinates, "
              "table cells and detailed diagnostics are available in the job artifacts.", ""]
    return "\n".join(lines)


def render_limited_overview(source, overview, source_locations, outcome, reason):
    if outcome.processing_status == "failed":
        heading = "Processing failed — limited overview only"
    elif outcome.status == "failed":
        heading = "Research readiness failed — limited overview only"
    else:
        heading = f"Limited overview only — research quality {outcome.status}"
    lines = [f"# {heading}", "", f"Source: {escape(source)}", ""]
    if overview:
        lines.append(escape(overview.overview))
        refs = [f"{source_id}; PDF p. {source_locations[source_id]}"
                for source_id in overview.source_ids if source_id in source_locations]
        if refs:
            lines[-1] += " [" + "; ".join(refs) + "]"
    else:
        lines.append("A limited overview could not be generated because readable text was insufficient or local Qwen was unavailable.")
    lines += ["", f"Reason: {escape(reason or 'The report did not meet research readiness checks.')}",
              "", "This orientation describes only the apparent subject and aim. It is not a validated research summary.",
              "No findings or statistical conclusions are established by this artifact.", ""]
    return "\n".join(lines)
