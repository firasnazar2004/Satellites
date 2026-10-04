"""Conservative evidence checks. Literal support is necessary, not semantic proof."""

import re

from app.models.research import GroundedEvidence
from app.pipelines.research_sources import EXCLUDED

NUMBER = r"[+−-]?(?:\d+(?:[.,]\d+)*|\.\d+)(?:[eE][+−-]?\d+)?"
NUMERIC_CATEGORIES = {"sample_size", "denominator", "percentage", "test_statistic",
                      "degrees_freedom", "p_value", "confidence_interval", "effect_size",
                      "diagnostic_accuracy"}
UNITS = r"patients?|participants?|subjects?|adults?|children|cases?|records?|files?|studies|trials|samples?|observations?|respondents?|neurons?|images?|datasets?"
MEASURES = {
    "sample_size": rf"(?:\b[Nn]\s*=\s*\d+|\b\d+[\s-]+(?:{UNITS})\b|\b\d+\s+(?:[A-Za-z][\w-]*\s+){{0,3}}(?:{UNITS})\b|\b\d+\s+(?:fit|met|included|eligible)\b|(?:sample size|enroll\w*|recruit\w*)[^.;]{{0,60}}?\d+)",
    "denominator": rf"(?:\b(?:of|among|out of|total(?: of)?|total count(?: of)?|total number(?: of)?)\s+\d+[\s-]+(?:{UNITS})\b|\btotal\s+(?:count|number)\s+of\s+(?:[A-Za-z-]+\s+){{0,3}}(?:{UNITS})\b[^.;]{{0,80}}?{NUMBER}|\b\d+\s*/\s*\d+|denominator\s*(?:of|=|:)\s*\d+)",
    "percentage": rf"{NUMBER}\s*(?:%|percent\b|per cent\b)",
    "p_value": rf"\b[pP](?:[- ]values?)?\s*(?:=|<=|>=|<|>|≤|≥|was|is|of)\s*{NUMBER}",
    "confidence_interval": rf"(?:\b(?:\d+(?:\.\d+)?\s*%\s*)?(?:confidence interval|CI)\b\s*(?:[:=]|was|is|of)?\s*[\[(]?\s*{NUMBER}\s*(?:,|;|to|[-–—])\s*{NUMBER})",
    "test_statistic": rf"(?:\b(?:chi[- ]?square(?:d)?|Pearson\s+Chi[- ]?Square|Likelihood\s+Ratio|χ[²2]?|chi2|[tFz])\b(?:\s*\([^)]{{1,35}}\))?(?:\s*\|\s*Value)?\s*[:=]\s*{NUMBER})",
    "degrees_freedom": rf"(?:\bdf\s*[:=]\s*{NUMBER}|\bdegrees?\s+of\s+freedom\s*[:=]?\s*{NUMBER})",
    "effect_size": rf"(?:Cohen[’']?s?\s*d|Hedges[’']?\s*g|odds ratio|risk ratio|hazard ratio|mean difference|Cram[eé]r[’']?s?\s*V|eta[- ]squared|epsilon[- ]squared|rank[- ]biserial|R[²2]|\br\b|\brho\b|\bOR\b|\bRR\b|\bHR\b)\s*(?:was|is|of|=|:)\s*{NUMBER}",
    "diagnostic_accuracy": rf"(?:(?:sensitivity|specificity|accuracy|AUC|positive predictive value|negative predictive value)\s*(?:was|is|of|=|:)?\s*{NUMBER}\s*%?|{NUMBER}\s*%\s*(?:sensitivity|specificity|accuracy))",
}
MEASURES["statistical_warning"] = r"\b(?:expected count|expected cell|minimum expected|cells?\s+have\s+expected|assumption|sparse cells?|small expected frequencies)\b[^.;]{0,180}"
CITED = re.compile(r"\bet\s*al\b|\b(?:previous|prior|earlier|another|other)\s+(?:stud(?:y|ies)|trial|research)|\b(?:according to|reported by)\b", re.I)
OWN = re.compile(r"\b(?:we|our|this study|present study|this paper|this review|we propose|we prove)\b", re.I)


def literal_span(value, text):
    """An exact bounded match; no fuzzy or numeric-equivalence acceptance."""
    for match in re.finditer(re.escape(value), text):
        start, end = match.span()
        if start and text[start-1].isalnum() and value[0].isalnum():
            continue
        if end < len(text) and text[end].isalnum() and value[-1].isalnum():
            continue
        if value[0].isdigit() and start and text[start-1] in ".,−-+":
            continue
        return start, end
    return None


def numerical_tokens(text):
    return re.findall(NUMBER, text)


def _context_window(text, start, end, width=180):
    """Retain the exact sentence/window that gives a measure its subgroup meaning."""
    if len(text) <= width * 2:
        return text.strip()
    left = max(text.rfind(". ", 0, start), text.rfind("; ", 0, start))
    left = 0 if left < 0 else left + 2
    right_candidates = [position for marker in (". ", "; ")
                        if (position := text.find(marker, end)) >= 0]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    if right - left > width * 2:
        left, right = max(0, start - width), min(len(text), end + width)
    return text[left:right].strip()


def _explicit_eligibility_pair(text):
    """Read a source-stated total-to-eligible count without calculating values."""
    link = re.search(
        r"\btotal\s+(?:count|number)\s+of\b[^.;]{0,120}?(?P<ofwhom>\bof\s+whom\b)"
        r"[^.;]{0,120}?\b(?:fit|met|satisfied)\b[^.;]{0,80}?\b(?:inclusion|exclusion|selection)\s+criteria\b",
        text, re.I)
    if not link:
        return None
    units = rf"(?:{UNITS})"
    before = text[link.start():link.start("ofwhom")]
    after = text[link.end("ofwhom"):link.end()]
    totals = list(re.finditer(rf"{NUMBER}\s+{units}\b", before, re.I))
    eligible = re.search(rf"{NUMBER}(?:\s+{units}\b)?", after, re.I)
    if not totals or not eligible:
        return None
    return totals[-1].group(), eligible.group()


GROUP_LABEL = re.compile(
    r"\b(?P<label>women|woman|females?|girls?|men|man|males?|boys?|"
    r"children|adolescents?|adults?|older adults?|elderly|patients?|controls?|"
    r"cases?|treated group|control group)\b", re.I)


def _explicit_subgroup(text, span):
    """Bind a subgroup only when nearby source wording connects it to the value."""
    prefix = text[max(0, span[0] - 120):span[0]]
    found = None
    for match in GROUP_LABEL.finditer(prefix):
        connector = prefix[match.end():]
        if len(connector) <= 55 and re.search(
                r"\b(?:had|was|were|at|reported|showed|constituting|constituted|"
                r"accounted\s+for|prevalence|rate|proportion)\b|[:=]", connector, re.I):
            found = match.group()
    return found


def validate_proposal(item, passage, *, source, evidence_id, document_type, span_bounds=None):
    reasons = []
    text, category = passage.text, item.category
    if span_bounds:
        fragment_start, fragment_end = span_bounds
        fragment_end = min(fragment_end, len(text))
        local_span = literal_span(item.value, text[fragment_start:fragment_end])
        span = ((fragment_start + local_span[0], fragment_start + local_span[1])
                if local_span else None)
    else:
        fragment_start, fragment_end = 0, len(text)
        span = literal_span(item.value, text)
    # A labelled source pool followed by an explicit eligible subset has two
    # different roles. Classify the first count as a denominator only when the
    # source states both the total group and an ``of whom ... criteria`` link.
    link_match = re.search(
        r"\btotal\s+(?:count|number)\s+of\b[^.;]{0,120}?(?P<ofwhom>\bof\s+whom\b)"
        r"[^.;]{0,120}?\b(?:fit|met|satisfied)\b[^.;]{0,80}?\b(?:inclusion|exclusion|selection)\s+criteria\b",
        text, re.I)
    eligibility_pair = _explicit_eligibility_pair(text)
    if (category == "sample_size" and span and link_match
            and span[1] <= link_match.start("ofwhom")):
        item = item.model_copy(update={"category": "denominator"})
        category = "denominator"
    if span is None:
        reasons.append("value_not_literal_in_selected_passage")
    if passage.section in EXCLUDED:
        reasons.append("excluded_document_section")
    if passage.section == "front_matter" and category != "metadata":
        reasons.append("front_matter_is_not_study_evidence")
    # Avoid title stubs and bibliography fragments even when perfectly quoted.
    if passage.kind == "text" and category != "metadata":
        count = len(text.split())
        concise_design = (category == "study_design" and bool(re.search(
            r"\b(?:cross[- ]?sectional|cohort|case[- ]control|randomi[sz]ed|"
            r"systematic review|meta[- ]analysis|clinical trial|convenience sampling|"
            r"probability sampling|purposive sampling)\b", text, re.I)))
        if not concise_design and (count < 4 or text.rstrip().endswith(":") or
                (count < 6 and not re.search(r"[.!?][\])\"']?$", text.rstrip()))):
            reasons.append("incomplete_fragment")
    if category in NUMERIC_CATEGORIES:
        if any(w.startswith("Numeric token discrepancy") for w in passage.warnings):
            if not set(numerical_tokens(item.value)) <= set(numerical_tokens(passage.raw_text)):
                reasons.append("numeric_extraction_discrepancy_requires_manual_review")
        if not numerical_tokens(item.value):
            reasons.append("quantitative_category_requires_explicit_numeric_value")
        pattern = MEASURES[category]
        if passage.kind == "table" and category == "percentage":
            pattern += rf"|\b(?:Valid Percent|Cumulative Percent|Percent(?:age)?)\s*:\s*{NUMBER}"
        if passage.kind == "table" and category == "sample_size":
            pattern += rf"|\bN of Valid Cases\s*\|\s*(?:Value\s*:\s*)?{NUMBER}"
            pattern += rf"|\bTotal\s*\|(?:[^|]+\|){{0,2}}\s*Frequency\s*:\s*{NUMBER}"
        if passage.kind == "table" and category == "p_value":
            pattern += rf"|(?:Asymp\.\s*Sig\.|Exact\s*Sig\.)(?:\s*\([^)]*\))?\s*:\s*{NUMBER}"
        if passage.kind == "table" and category == "test_statistic":
            pattern += rf"|\b(?:Pearson\s+Chi[- ]?Square|Likelihood\s+Ratio)\s*\|\s*(?:Value\s*:\s*)?{NUMBER}[a-z]?"
        matches = list(re.finditer(pattern, text, re.I))
        # The value must touch the labelled measure; an unrelated number elsewhere
        # in the paragraph cannot borrow a label or a significance symbol.
        item_numbers = set(numerical_tokens(item.value))
        supported_matches = [m for m in matches if span and m.start() >= fragment_start
                             and m.end() <= fragment_end and m.start() < span[1]
                             and m.end() > span[0]
                             and item_numbers & set(numerical_tokens(m.group()))]
        supported_numbers = {number for m in supported_matches for number in numerical_tokens(m.group())
                             if number in item_numbers}
        # Parenthetical labels such as ``(2-sided)`` are not additional
        # p-values. The validated p-value is the final numeric token in the
        # explicitly labelled measure.
        if category in {"p_value", "degrees_freedom"}:
            supported_numbers = {tokens[-1] for match in supported_matches
                                 if (tokens := numerical_tokens(match.group()))}
        if not supported_matches:
            reasons.append("missing_local_measure_label_or_supported_measure_shape")
        elif len(supported_numbers) > 1 and category not in {"confidence_interval", "test_statistic"}:
            reasons.append("ambiguous_multiple_numeric_values")
        if span and (re.search(r"\[\s*\d+(?:\s*[,–-]\s*\d+)*\s*\]", item.value)
                     or re.search(r"(?:ref(?:erence)?\.?|citation)\s*$", text[max(0, span[0]-15):span[0]], re.I)):
            reasons.append("citation_is_not_a_measure")
        if category == "p_value":
            for match in supported_matches:
                value = numerical_tokens(match.group())[-1]
                try:
                    if not 0 <= float(value.replace("−", "-")) <= 1:
                        reasons.append("p_value_outside_unit_interval")
                except ValueError:
                    reasons.append("unsupported_p_value_notation")
        if category == "percentage" and span:
            local = text[max(0, span[0]-80):min(len(text), span[1]+80)]
            if re.search(r"\b(?:sensitivity|specificity|accuracy|AUC|"
                         r"positive predictive value|negative predictive value)\b", local, re.I):
                reasons.append("percentage_is_a_more_specific_diagnostic_measure")
        if span and passage.kind == "text" and text.count(item.value) > 1:
            reasons.append("ambiguous_repeated_value_requires_context")
    checks = {
        "objective": r"\b(?:aim|objective|purpose|question|investigat|examin|propos|study whether|determin|assess|evaluat|estimat|identif|quantif|explor)",
        "study_design": r"\b(?:cross[- ]?sectional|cohort|case[- ]control|randomi[sz]|trial|retrospective|prospective|survey|sampling|systematic review|meta[- ]analysis|proof|theorem|framework|experiment|method)",
        "limitation": r"\b(?:limitation|limited|missing|bias|caution|uncertain|not recorded|not measured|small sample|expected count|cannot|could not|not generaliz|not generalis)",
        "population": rf"\b(?:{UNITS}|population|clinic|athlete|setting|eligib|inclusion|exclusion)\b",
    }
    if category == "statistical_warning" and not re.search(MEASURES[category], item.value, re.I):
        reasons.append("statistical_warning_requires_explicit_caveat_wording")
    if category in checks and not re.search(checks[category], item.value, re.I):
        reasons.append("category_not_supported_by_selected_value")
    if category == "metadata" and passage.page > 2 and passage.section != "front_matter":
        reasons.append("metadata_outside_front_matter")
    if category in {"finding", "conclusion"} and passage.section == "methods":
        reasons.append("methods_passage_is_not_a_finding")
    if item.origin == "current_study":
        local_text = text[max(0, span[0]-110):min(len(text), span[1]+110)] if span else item.value
        if CITED.search(local_text):
            reasons.append("cited_study_cannot_be_claimed_as_current_study")
        if passage.section in {"front_matter", "introduction"}:
            if category not in {"metadata", "objective"}:
                reasons.append("background_section_requires_background_or_cited_attribution")
        if (document_type == "unknown" and passage.section not in {"results", "conclusions"}
                and not OWN.search(text) and category in {"finding", "conclusion"}):
            reasons.append("unknown_document_requires_explicit_current_work_attribution")
        if passage.section == "discussion" and not OWN.search(text) and re.search(
                r"\[\d+\]|\([A-Z][^)]{0,80}\b(?:19|20)\d{2}\)", text):
            reasons.append("discussion_citation_requires_explicit_current_work_attribution")
    if item.origin == "cited_study":
        if not item.attribution or literal_span(item.attribution, text) is None:
            reasons.append("cited_finding_requires_literal_author_or_citation_attribution")
        elif not (re.search(r"\[\s*\d+|\bet\s*al\b|\b(?:19|20)\d{2}\b", item.attribution, re.I)
                  or re.search(r"\b[A-Z][a-z]+", item.attribution)):
            reasons.append("attribution_is_not_recognizable_as_author_or_citation")
    elif item.attribution:
        reasons.append("attribution_only_for_cited_studies")
    if reasons:
        return None, sorted(set(reasons))
    if category in NUMERIC_CATEGORIES and supported_matches:
        # Store the shortest exact labelled measure for the requested type.
        # Subgroup, denominator and comparison wording remains in context_text.
        measure = min(supported_matches, key=lambda match: len(match.group()))
        unrelated = set(numerical_tokens(item.value)) - set(numerical_tokens(measure.group()))
        if len(item.value) > 90 or unrelated:
            item = item.model_copy(update={"value": measure.group()})
            span = measure.span()
    warnings = list(passage.warnings)
    if passage.kind == "table":
        warnings.append("Table measures use explicit labels; header association and footnotes require review")
    if re.search(r"strong\s+association|caus(?:e|ed|al)|risk factor", text, re.I):
        warnings.append("Author wording retained; p-values do not establish strength or causality")
    measure = None
    if category in NUMERIC_CATEGORIES:
        from app.models.research import ReportedMeasure
        match = supported_matches[0] if supported_matches else None
        explicit_denominator = explicit_subgroup = None
        if eligibility_pair and category in {"sample_size", "denominator"}:
            total_value, eligible_value = eligibility_pair
            item_numbers = set(numerical_tokens(item.value))
            if category == "sample_size" and item_numbers & set(numerical_tokens(eligible_value)):
                explicit_denominator = total_value
            elif category == "denominator" and item_numbers & set(numerical_tokens(total_value)):
                explicit_subgroup = eligible_value
        literal_subgroup = (_explicit_subgroup(text, span)
                            if span and category in {"sample_size", "denominator", "percentage",
                                                     "diagnostic_accuracy"} else None)
        explicit_subgroup = explicit_subgroup or literal_subgroup
        has_explicit_relation = bool(explicit_denominator or explicit_subgroup)
        measure = ReportedMeasure(role=category, exact_text=match.group() if match else item.value,
            label=(match.group(0).split(":", 1)[0].split("=", 1)[0].strip()
                   if match and (":" in match.group() or "=" in match.group()) else None),
            operator=next((op for op in ("<=", ">=", "≤", "≥", "<", ">", "=")
                           if match and op in match.group()), "reported"),
            denominator=explicit_denominator, subgroup=explicit_subgroup,
            relation_source_ids=[passage.id] if has_explicit_relation else [],
            relation_status="explicit" if has_explicit_relation else "unresolved")
    return GroundedEvidence(**item.model_dump(), measure=measure, id=evidence_id, source=source,
        page=passage.page, section=passage.section, source_kind=passage.kind, quote=text,
        value_start=span[0], value_end=span[1], context_ids=passage.context_ids,
        context_text=_context_window(text, span[0], span[1]),
        warnings=warnings), []


def duplicate_of(record, records):
    """Keep differing subgroup/context passages even if scalar values coincide."""
    return next((old for old in records if old.category == record.category
            and old.origin == record.origin and old.attribution == record.attribution
            and old.value == record.value and old.context_text == record.context_text
            and old.passage_id == record.passage_id), None)


def deduplicate(records):
    """Only literal equality/containment, never fuzzy matching of numerical facts."""
    kept = []
    for record in records:
        if duplicate_of(record, kept) is None:
            kept.append(record)
    return kept
