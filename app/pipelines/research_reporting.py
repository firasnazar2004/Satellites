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
    "degrees_freedom", "confidence_interval", "effect_size", "diagnostic_accuracy",
}
RESULT_CATEGORIES = {
    "finding", "percentage", "test_statistic", "p_value", "confidence_interval",
    "effect_size", "diagnostic_accuracy",
}
NUMBER_TOKEN = re.compile(
    r"(?<![A-Za-z0-9.])[+−-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?![A-Za-z0-9%])"
)
NUMBER_WORD = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million)\b",
    re.I,
)
CONTENT_WORD = re.compile(r"[A-Za-z][A-Za-z-]{2,}")
STOP_WORDS = {"the", "and", "for", "that", "this", "with", "from", "were", "was",
              "study", "paper", "result", "results", "found", "reported", "within"}
GROUP_ALIASES = {
    "woman": "female", "women": "female", "girl": "female", "girls": "female",
    "female": "female", "females": "female", "man": "male", "men": "male",
    "boy": "male", "boys": "male", "male": "male", "males": "male",
    "adult": "adult", "adults": "adult", "child": "child", "children": "child",
    "adolescent": "adolescent", "adolescents": "adolescent", "patient": "patient",
    "patients": "patient", "control": "control", "controls": "control",
}
GROUP_TERM = re.compile(r"\b(?:women?|females?|girls?|men|males?|boys?|placebo|controls?)\b", re.I)


def _group_terms(text):
    return {GROUP_ALIASES.get(match.group().casefold(), match.group().casefold())
            for match in GROUP_TERM.finditer(text)}


def _unsupported_figures(claim, evidence):
    """Return figures/number words not literally supported by cited numeric records."""
    cited_items = [evidence[evidence_id] for evidence_id in claim.evidence_ids
                   if evidence_id in evidence and evidence[evidence_id]["category"]
                   in NUMERIC_CATEGORIES | {"statistical_warning"}]
    cited_values = [item["value"] for item in cited_items]
    for item in cited_items:
        measure = item.get("measure") or {}
        cited_values.append(measure.get("exact_text", ""))
        relation_sources = set(measure.get("relation_source_ids", []))
        if (measure.get("relation_status") == "explicit" and relation_sources
                and relation_sources <= set(claim.source_ids)):
            cited_values.extend((measure.get("denominator") or "", measure.get("subgroup") or ""))
    allowed = {
        match.group().casefold() for value in cited_values for match in NUMBER_TOKEN.finditer(value)
    }
    unsupported = {match.group() for match in NUMBER_TOKEN.finditer(claim.text)
                   if match.group().casefold() not in allowed}
    supported_text = " ".join(cited_values).casefold()
    unsupported.update(match.group() for match in NUMBER_WORD.finditer(claim.text)
                       if match.group().casefold() not in supported_text)
    return unsupported


def _terms(text):
    return {word.casefold() for word in CONTENT_WORD.findall(text)
            if word.casefold() not in STOP_WORDS}


def select_evidence(records, document_type, limit=9):
    """Reserve space for the question, design, central results, context and caveats."""
    candidates = [e for e in records if e.origin == "current_study" or
                  (document_type == "review" and e.origin == "cited_study")]
    section_score = {"abstract": 9, "results": 8, "conclusions": 6, "limitations": 7,
                     "methods": 5, "discussion": 4, "introduction": 3, "front_matter": 0}

    objective_terms = set().union(*(_terms(e.value + " " + e.quote) for e in candidates
                                    if e.category == "objective"))

    def rank(e):
        value_text = e.value.casefold()
        overlap = len(objective_terms & _terms(e.context_text or e.quote))
        central = 5 if re.search(
            r"\b(?:primary|main|overall|prevalence|incidence|principal|most common|found to be)\b",
            value_text, re.I) else 0
        return (section_score.get(e.section, 1) + (2 if e.importance == "primary" else 0)
                + central + min(overlap, 4), e.origin == "current_study",
                bool(e.context_text), e.source_kind == "text", -e.page, -len(e.quote))

    ranked = sorted(candidates, key=rank, reverse=True)
    selected, used, per_passage = [], set(), Counter()

    def add(record, *, bundle=False):
        key = (record.passage_id, record.category, record.value, record.context_text)
        passage_limit = 5 if bundle or record.category in {
            "test_statistic", "p_value", "degrees_freedom", "statistical_warning"} else 2
        if key in used or len(selected) >= limit or per_passage[record.passage_id] >= passage_limit:
            return
        used.add(key)
        selected.append(record)
        per_passage[record.passage_id] += 1

    # Keep the best explicit question first, then select central results with
    # their directly linked statistical/denominator context as compact bundles.
    objective = next((e for e in ranked if e.category == "objective"), None)
    if objective:
        add(objective)
    inferential = [e for e in ranked if e.category in {
        "test_statistic", "p_value", "degrees_freedom", "statistical_warning"}]
    processed_inferential = set()
    for record in inferential:
        if record.id in processed_inferential:
            continue
        if len(selected) >= max(1, limit - 4):
            break
        add(record, bundle=True)
        linked_ids = set(getattr(record, "context_ids", []) or []) | {record.passage_id}
        for companion in inferential:
            if companion is record:
                continue
            if companion.passage_id in linked_ids or record.passage_id in (
                    getattr(companion, "context_ids", []) or []):
                add(companion, bundle=True)
                processed_inferential.add(companion.id)
        processed_inferential.add(record.id)
    central = [e for e in ranked if e.category in RESULT_CATEGORIES
               and e.section in {"abstract", "results", "discussion", "conclusions"}
               and e not in selected]
    supporting_categories = {"study_design", "population", "sample_size", "denominator",
                            "conclusion", "limitation"}
    supporting_available = sum(1 for item in ranked if item.category in supporting_categories)
    seed_limit = max(1, min(3, limit - len(selected) - supporting_available))
    seeds = []
    for record in central:
        if record.passage_id in {item.passage_id for item in seeds}:
            continue
        add(record)
        if record in selected:
            seeds.append(record)
        if len(seeds) >= seed_limit:
            break
    for record in seeds:
        linked_ids = set(getattr(record, "context_ids", []) or []) | {record.passage_id}
        companions = [item for item in ranked if item is not record and
            item.category in {"sample_size", "denominator", "test_statistic", "p_value",
                              "degrees_freedom", "statistical_warning", "confidence_interval",
                              "effect_size", "diagnostic_accuracy"} and
            (item.passage_id in linked_ids or record.passage_id in
             (getattr(item, "context_ids", []) or []))]
        for companion in companions:
            add(companion, bundle=True)

    # Fill remaining capacity by objective relevance and document coverage.
    supporting = {"study_design", "population", "sample_size", "denominator",
                  "conclusion", "limitation", "degrees_freedom", "statistical_warning"}
    for record in ranked:
        if record.category in supporting:
            add(record, bundle=record.category in {"degrees_freedom", "statistical_warning"})
    for record in ranked:
        if record.category != "metadata":
            add(record)
    return selected


def assess_coverage(records, selected, document_type, *, extraction_complete,
                    problems, rejected_attempts, eligible_passages, pages,
                    processing_error=None):
    own = [e for e in records if e.origin == "current_study"]
    reportable = own if document_type != "review" else [
        e for e in records if e.origin in {"current_study", "cited_study"}
    ]
    coverage = {
        "objective": any(e.category == "objective" for e in own),
        "methods": any(e.category == "study_design" for e in own),
        "population": any(e.category in {"population", "sample_size", "denominator"} for e in own),
        "findings": any(e.category in RESULT_CATEGORIES for e in reportable),
        "conclusions": any(e.category == "conclusion" for e in own),
        "limitations": any(e.category == "limitation" for e in own),
        "cited_findings": any(e.origin == "cited_study" for e in records),
        "central_findings": any(
            (e.origin == "current_study" or document_type == "review")
            and e.section in {"abstract", "results", "discussion", "conclusions"}
            and e.category in RESULT_CATEGORIES
            for e in reportable
        ),
        "objective_result_linked": any(
            bool(_terms(objective.value + " " + objective.quote) &
                 _terms(result.context_text or result.quote))
            for objective in own if objective.category == "objective"
            for result in reportable if result.category in RESULT_CATEGORIES
            and result.section in {"abstract", "results", "discussion", "conclusions"}
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

    core = ("objective", "methods", "findings") if document_type in {"empirical", "unknown"} \
        else ("objective", "findings")
    missing = [name for name in core if not coverage[name]]
    if not processing_error:
        if not coverage["central_findings"]:
            missing.append("central_claims_not_adequately_attributed_in_principal_sections")
        if coverage["objective"] and coverage["central_findings"] and not coverage["objective_result_linked"]:
            missing.append("no_lexical_link_between_objective_and_selected_central_results")
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
    central_records = [e for e in reportable
        if e.section in {"abstract", "results", "discussion", "conclusions"}
        and e.category in RESULT_CATEGORIES]
    substantive = coverage["central_findings"] and any(
        e.category in RESULT_CATEGORIES and
        (e.origin == "current_study" or document_type == "review") for e in selected)
    # One isolated result cannot establish adequacy. Multiple central records
    # can remain useful as partial quality when the objective is absent or unclear.
    adequate_attribution = substantive and (coverage["objective_result_linked"]
                                             or len(central_records) >= 2)
    if processing_error:
        status = "failed"
        reasons = ["Processing failed before a validated report could be completed"]
    elif not adequate_attribution:
        status = "failed"
        reasons.append("Required attributable central evidence was not established")
    elif missing or source_issues or document_type == "unknown" or not coverage["objective_result_linked"]:
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
        for context_id in (getattr(record, "context_ids", None) or [])[:3]:
            passage = by_id.get(context_id)
            if passage is None:
                unresolved.append(context_id)
                continue
            context.append({
                "id": passage.id, "page": passage.page, "section": passage.section,
                "kind": getattr(passage, "kind", "text"),
                "table_id": getattr(passage, "table_id", None), "text": passage.text[:320],
            })
            source_ids.append(passage.id)
        focused_source = (record.context_text or record.quote)[:700]
        item = {
            "evidence_id": record.id, "passage_id": record.passage_id, "page": record.page,
            "section": record.section, "category": record.category, "origin": record.origin,
            "attribution": record.attribution, "importance": record.importance, "value": record.value,
            "measure": record.measure.model_dump() if getattr(record, "measure", None) else None,
            "source_text": focused_source,
            "source_context": (record.context_text[:700]
                               if record.context_text and record.context_text != focused_source else ""),
            "extraction_method": record.extraction_method,
            "source_ids": source_ids, "context": context,
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


def validate_narrative_issues(narrative, payload):
    evidence = {item["evidence_id"]: item for item in payload if "evidence_id" in item}
    source_ids = {source_id for item in evidence.values() for source_id in item["source_ids"]}
    issues, claims = [], []

    def add(code, message, section=None, claim=None, details=None):
        issues.append({"code": code, "message": message, "section": section,
                       "claim": claim.text if claim else None, "details": details or {}})
    section_categories = {
        "introduction": {"objective", "study_design", "finding", "conclusion"},
        "methods_scope": {"study_design", "population", "sample_size", "denominator"},
        "key_findings": {"finding", *NUMERIC_CATEGORIES, "conclusion", "study_design",
                         "population", "sample_size", "denominator"},
        "statistical_information": NUMERIC_CATEGORIES | {"statistical_warning"},
        "conclusion": {"finding", "conclusion", "limitation", *NUMERIC_CATEGORIES},
    }
    for section in ("introduction", "methods_scope", "key_findings",
                    "statistical_information", "conclusion"):
        value = getattr(narrative, section)
        claims.extend((section, claim) for claim in (
            [value] if section == "introduction" and value else value or []))
    for section, claim in claims:
        unsupported = sorted(_unsupported_figures(claim, evidence))
        if unsupported:
            add("unsupported_figure",
                "Narrative figure is not an exact value in its cited numeric evidence",
                section, claim, {"unsupported": unsupported,
                    "cited_evidence_ids": claim.evidence_ids})
        if claim is narrative.introduction:
            sentences = len(re.findall(r"[.!?](?:\s|$)", claim.text.strip())) or 1
            if len(claim.text) > 450 or sentences > 3:
                add("introduction_too_long", "Introduction must be one short, accessible paragraph",
                    section, claim)
        if not set(claim.evidence_ids) <= evidence.keys():
            add("unknown_evidence_id", "Narrative cites an evidence ID not supplied to synthesis",
                section, claim, {"unknown": sorted(set(claim.evidence_ids) - evidence.keys())})
            continue
        if not set(claim.source_ids) <= source_ids:
            add("unknown_source_id", "Narrative cites a source passage not supplied to synthesis",
                section, claim, {"unknown": sorted(set(claim.source_ids) - source_ids)})
            continue
        for evidence_id in claim.evidence_ids:
            if evidence[evidence_id]["category"] not in section_categories[section]:
                add("incompatible_category",
                    f"Narrative uses an incompatible evidence category in {section}",
                    section, claim, {"evidence_id": evidence_id,
                                     "category": evidence[evidence_id]["category"]})
            if section == "key_findings":
                categories = {evidence[item_id]["category"] for item_id in claim.evidence_ids}
                substantive = {"finding", *NUMERIC_CATEGORIES, "conclusion"}
                if not categories & substantive:
                    add("context_does_not_authorize_finding",
                        "Methods, population, and denominator context cannot stand alone as a finding",
                        section, claim)
            cited_record = evidence[evidence_id]
            claim_groups = _group_terms(claim.text)
            if claim_groups and cited_record["category"] in NUMERIC_CATEGORIES:
                measure = cited_record.get("measure") or {}
                source_groups = _group_terms(measure.get("subgroup") or "")
                if not source_groups or not claim_groups <= source_groups:
                    add("unsupported_subgroup_binding",
                        "A subgroup claim must match an explicit source-linked measure subgroup",
                        section, claim, {"claim_groups": sorted(claim_groups),
                                         "measure_subgroup": measure.get("subgroup")})
            claim_categories = {evidence[item_id]["category"] for item_id in claim.evidence_ids}
            if ("p_value" in claim_categories and not claim_categories & {"finding", "effect_size"}
                    and re.search(r"\b(?:caus(?:e|es|ed|al)|strong(?:er)?|weak(?:er)?|large|small)\b",
                                  claim.text, re.I)):
                add("p_value_overinterpretation",
                    "A p-value alone cannot support a causal or association-strength claim",
                    section, claim)
            study_designs = [evidence[item_id] for item_id in claim.evidence_ids
                             if evidence[item_id]["category"] == "study_design"]
            causal_language = re.search(r"\bcaus(?:e|es|ed|al)\b", claim.text, re.I)
            observational = any(re.search(
                r"\b(?:observational|cross[- ]?sectional|cohort|case[- ]control|survey|"
                r"retrospective|prospective)\b",
                item.get("value", "") + " " + item.get("source_text", ""), re.I)
                for item in study_designs)
            cited_source_text = " ".join(evidence[item_id].get("source_text", "") + " " +
                                          evidence[item_id].get("value", "")
                                          for item_id in claim.evidence_ids)
            source_states_causality = bool(re.search(r"\bcaus(?:e|es|ed|al)\b",
                                                      cited_source_text, re.I))
            attributes_to_authors = bool(re.search(
                r"\b(?:authors?|paper|study)\s+(?:reported|stated|claimed|concluded|argued)\b",
                claim.text, re.I))
            if causal_language and (observational or not source_states_causality
                                    or not attributes_to_authors):
                add("unsupported_causal_claim",
                    "Causal wording needs explicit source attribution and cannot be inferred from observational evidence",
                    section, claim)
            if not set(claim.source_ids) & set(evidence[evidence_id]["source_ids"]):
                add("unlinked_citation", f"Narrative citation does not link to evidence {evidence_id}",
                    section, claim, {"evidence_id": evidence_id})
            item = evidence[evidence_id]
            if item.get("origin") == "cited_study":
                attribution = item.get("attribution") or ""
                if not ((attribution and attribution.casefold() in claim.text.casefold())
                        or re.search(r"\b(?:prior|previous|earlier|cited)\s+(?:study|research|work)\b",
                                     claim.text, re.I)):
                    add("missing_cited_study_attribution",
                        f"Cited-study claim lacks explicit attribution for {evidence_id}",
                        section, claim, {"evidence_id": evidence_id})
    if narrative.introduction is None:
        add("missing_introduction", "Narrative introduction is missing")
    if not narrative.key_findings:
        add("missing_key_findings", "Narrative key findings are missing")
    key_finding_ids = {evidence_id for claim in narrative.key_findings
                       for evidence_id in claim.evidence_ids}
    primary_current_ids = {item["evidence_id"] for item in evidence.values()
        if item.get("origin") == "current_study" and item.get("importance") == "primary"
        and item.get("category") in {"finding", *NUMERIC_CATEGORIES, "conclusion"}}
    if primary_current_ids and not key_finding_ids & primary_current_ids:
        add("missing_primary_evidence", "Key findings omit the supplied primary current-study evidence",
            details={"primary_evidence_ids": sorted(primary_current_ids)})
    unique = {}
    for issue in issues:
        key = (issue["code"], issue["section"], issue["claim"], repr(issue["details"]))
        unique[key] = issue
    return list(unique.values())


def validate_narrative(narrative, payload):
    return sorted({issue["message"] for issue in validate_narrative_issues(narrative, payload)})


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


def _numeric_context(record, selected, width=90):
    """Show context while suppressing source numbers not represented by typed facts."""
    if record.context_text:
        excerpt = record.context_text
    else:
        start = max(0, record.value_start - width)
        end = min(len(record.quote), record.value_end + width)
        excerpt = record.quote[start:end].strip()
        excerpt = ("…" if start else "") + excerpt + ("…" if end < len(record.quote) else "")
    related_ids = set(getattr(record, "context_ids", []) or [])
    authorized = {match.group().casefold() for match in NUMBER_TOKEN.finditer(record.value)}
    if getattr(record, "measure", None):
        authorized.update(match.group().casefold() for match in NUMBER_TOKEN.finditer(
            record.measure.exact_text))
    for item in selected:
        explicit_context_link = (item.passage_id in related_ids or
                                 record.passage_id in (getattr(item, "context_ids", []) or []))
        same_table_row = (record.source_kind == item.source_kind == "table"
                          and record.passage_id == item.passage_id)
        if explicit_context_link or same_table_row:
            authorized.update(match.group().casefold() for match in NUMBER_TOKEN.finditer(item.value))
            if getattr(item, "measure", None):
                measure = item.measure
                authorized.update(match.group().casefold() for match in NUMBER_TOKEN.finditer(measure.exact_text))
        measure = getattr(record, "measure", None)
        if (measure and measure.relation_status == "explicit"
                and record.passage_id in measure.relation_source_ids):
            for related_value in (measure.denominator, measure.subgroup):
                authorized.update(match.group().casefold() for match in NUMBER_TOKEN.finditer(
                    related_value or ""))
    return NUMBER_TOKEN.sub(lambda match: match.group() if match.group().casefold() in authorized
                            else "[unvalidated value omitted]", excerpt)


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
                          f"{escape(_numeric_context(evidence, selected))} "
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
        heading = "Research report unavailable — limited overview only"
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
