import Foundation

struct APIClient: Sendable {
    let baseURL: URL
    let apiKey: String
    var session: URLSession = .shared

    init(baseURL: URL, apiKey: String, session: URLSession = .shared) {
        self.baseURL = baseURL.normalizedBaseURL
        self.apiKey = apiKey
        self.session = session
    }

    func get<T: Decodable>(_ path: String, as type: T.Type, timeout: TimeInterval = 60) async throws -> T {
        let data = try await data(for: request(path: path, method: "GET", timeout: timeout))
        return try decode(T.self, from: data)
    }

    func uploadFlashcards(fileURL: URL, cardsPerChunk: Int, maxChunkChars: Int) async throws -> Job {
        guard fileURL.pathExtension.lowercased() == "txt" else {
            throw APIError.invalidInputFile
        }

        var form = MultipartFormData()
        form.appendField(name: "cards_per_chunk", value: String(cardsPerChunk))
        form.appendField(name: "max_chunk_chars", value: String(maxChunkChars))
        try form.appendFile(
            name: "file",
            fileURL: fileURL,
            filename: fileURL.lastPathComponent,
            contentType: "text/plain; charset=utf-8"
        )

        var request = request(path: "/pipelines/flashcards", method: "POST", timeout: 60)
        request.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        request.httpBody = form.finalize()

        let data = try await data(for: request, expectedStatus: 202)
        return try decode(Job.self, from: data)
    }

    func uploadResearch(
        fileURL: URL,
        maxChunkChars: Int,
        documentType: ResearchDocumentType,
        readingOrder: ResearchReadingOrder
    ) async throws -> Job {
        guard fileURL.pathExtension.lowercased() == "pdf" else {
            throw APIError.validation("Choose a .pdf file for Research.")
        }

        var form = MultipartFormData()
        form.appendField(name: "max_chunk_chars", value: String(maxChunkChars))
        form.appendField(name: "document_type", value: documentType.rawValue)
        form.appendField(name: "reading_order", value: readingOrder.rawValue)
        try form.appendFile(
            name: "file",
            fileURL: fileURL,
            filename: fileURL.lastPathComponent,
            contentType: "application/pdf"
        )

        var request = request(path: "/pipelines/research", method: "POST", timeout: 60)
        request.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        request.httpBody = form.finalize()

        let data = try await data(for: request, expectedStatus: 202)
        return try decode(Job.self, from: data)
    }

    func downloadArtifact(_ artifact: Artifact) async throws -> Data {
        do {
            return try await data(for: request(path: artifact.url, method: "GET", timeout: 60))
        } catch let error as APIError {
            throw APIError.artifactDownloadFailure(error.localizedDescription)
        } catch {
            throw APIError.artifactDownloadFailure(nil)
        }
    }

    func streamChat(_ chatRequest: ChatStreamRequest) async throws -> URLSession.AsyncBytes {
        var request = request(path: "/chat/stream", method: "POST", timeout: 180)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/x-ndjson", forHTTPHeaderField: "Accept")
        request.httpBody = try Self.encoder.encode(chatRequest)

        do {
            let (bytes, response) = try await session.bytes(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                throw APIError.invalidResponse
            }
            guard httpResponse.statusCode == 200 else {
                var errorData = Data()
                for try await byte in bytes {
                    errorData.append(byte)
                }
                throw mapHTTPError(statusCode: httpResponse.statusCode, data: errorData)
            }
            return bytes
        } catch let error as APIError {
            throw error
        } catch let error as URLError where error.code == .appTransportSecurityRequiresSecureConnection {
            throw APIError.insecureHTTPBlocked
        } catch let error as POSIXError where error.code == .EPERM {
            throw APIError.networkPermissionDenied
        } catch let error as NSError where error.domain == NSPOSIXErrorDomain && error.code == Int(EPERM) {
            throw APIError.networkPermissionDenied
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            throw APIError.serverUnreachable
        }
    }

    func resolvedURL(for path: String) throws -> URL {
        if let absolute = URL(string: path), absolute.scheme != nil {
            return absolute
        }
        guard let url = URL(string: path, relativeTo: baseURL)?.absoluteURL else {
            throw APIError.invalidServerURL
        }
        return url
    }

    private func request(path: String, method: String, timeout: TimeInterval) -> URLRequest {
        let url = (try? resolvedURL(for: path)) ?? baseURL
        var request = URLRequest(url: url, timeoutInterval: timeout)
        request.httpMethod = method
        request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        return request
    }

    private func data(for request: URLRequest, expectedStatus: Int = 200) async throws -> Data {
        do {
            let (data, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                throw APIError.invalidResponse
            }
            guard httpResponse.statusCode == expectedStatus else {
                throw mapHTTPError(statusCode: httpResponse.statusCode, data: data)
            }
            return data
        } catch let error as APIError {
            throw error
        } catch let error as URLError where error.code == .appTransportSecurityRequiresSecureConnection {
            throw APIError.insecureHTTPBlocked
        } catch let error as POSIXError where error.code == .EPERM {
            throw APIError.networkPermissionDenied
        } catch let error as NSError where error.domain == NSPOSIXErrorDomain && error.code == Int(EPERM) {
            throw APIError.networkPermissionDenied
        } catch {
            throw APIError.serverUnreachable
        }
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        do {
            return try Self.decoder.decode(type, from: data)
        } catch {
            throw APIError.decodingFailed(error.localizedDescription)
        }
    }

    private func mapHTTPError(statusCode: Int, data: Data) -> APIError {
        let detail = (try? Self.decoder.decode(APIErrorDetail.self, from: data))?.detail.safeMessage
        switch statusCode {
        case 401:
            return .authenticationFailed
        case 403:
            return .forbidden
        case 404:
            return .notFound(detail)
        case 409:
            return .serverBusy(detail)
        case 413:
            return .uploadTooLarge
        case 422:
            return .validation(detail)
        case 502:
            return .badGateway(detail)
        case 503:
            return .serviceUnavailable(detail)
        default:
            if (400..<500).contains(statusCode) {
                return .uploadRejected(detail)
            }
            return .unknownStatus(statusCode, detail)
        }
    }

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()

    private static let encoder = JSONEncoder()
}

private extension URL {
    var normalizedBaseURL: URL {
        var absoluteString = absoluteString
        while absoluteString.hasSuffix("/") {
            absoluteString.removeLast()
        }
        return URL(string: absoluteString) ?? self
    }
}
