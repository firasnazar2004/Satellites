import Foundation

enum ResearchDocumentType: String, Codable, CaseIterable, Identifiable, Sendable {
    case auto
    case empirical
    case review
    case theoretical

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .auto: "Auto"
        case .empirical: "Empirical"
        case .review: "Review"
        case .theoretical: "Theoretical"
        }
    }
}

enum ResearchReadingOrder: String, Codable, CaseIterable, Identifiable, Sendable {
    case auto
    case single
    case two
    case three

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .auto: "Auto"
        case .single: "Single column"
        case .two: "Two columns"
        case .three: "Three columns"
        }
    }
}

enum ResearchQualityStatus: String, Codable, Sendable {
    case completed
    case partial
    case failed
    case unknown

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        let rawValue = try container.decode(String.self)
        self = ResearchQualityStatus(rawValue: rawValue) ?? .unknown
    }

    var displayName: String {
        switch self {
        case .completed: "Complete"
        case .partial: "Partial"
        case .failed: "Failed"
        case .unknown: "Unknown"
        }
    }
}

enum ResearchCoverageAssessment: String, Codable, Sendable {
    case supported
    case notReported = "not_reported"
    case notExtracted = "not_extracted"
    case uncertain
    case notApplicable = "not_applicable"
    case unknown

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        let rawValue = try container.decode(String.self)
        self = ResearchCoverageAssessment(rawValue: rawValue) ?? .unknown
    }

    var displayName: String {
        switch self {
        case .supported: "Supported"
        case .notReported: "Not reported"
        case .notExtracted: "Not extracted"
        case .uncertain: "Uncertain"
        case .notApplicable: "Not applicable"
        case .unknown: "Unknown"
        }
    }
}

struct ResearchResult: Codable, Sendable {
    let schema_version: String?
    let status: ResearchQualityStatus?
    let processing_status: String?
    let processing_error: String?
    let document_type: String?
    let reasons: [String]?
    let missing_coverage: [String]?
    let coverage: [String: Bool]?
    let coverage_assessment: [String: ResearchCoverageAssessment]?
    let source_quality_issues: [String]?
    let accepted_records: Int?
    let rejected_attempts: Int?
    let selected_records: Int?
    let extraction_complete: Bool?
}

extension ResearchResult {
    var qualityDisplayName: String {
        status?.displayName ?? "Unknown"
    }

    var documentTypeDisplayName: String {
        document_type?.capitalized ?? "Unknown"
    }

    var hasWarnings: Bool {
        status == .partial || status == .failed || !(missing_coverage ?? []).isEmpty || !(reasons ?? []).isEmpty
    }
}
