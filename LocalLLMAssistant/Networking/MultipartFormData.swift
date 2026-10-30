import Foundation

struct MultipartFormData {
    private let boundary = "Boundary-\(UUID().uuidString)"
    private var body = Data()

    var contentType: String {
        "multipart/form-data; boundary=\(boundary)"
    }

    mutating func appendField(name: String, value: String) {
        appendBoundary()
        body.appendString("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
        body.appendString("\(value)\r\n")
    }

    mutating func appendFile(name: String, fileURL: URL, filename: String, contentType: String) throws {
        appendBoundary()
        body.appendString("Content-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\n")
        body.appendString("Content-Type: \(contentType)\r\n\r\n")
        body.append(try Data(contentsOf: fileURL))
        body.appendString("\r\n")
    }

    mutating func finalize() -> Data {
        body.appendString("--\(boundary)--\r\n")
        return body
    }

    private mutating func appendBoundary() {
        body.appendString("--\(boundary)\r\n")
    }
}

private extension Data {
    mutating func appendString(_ string: String) {
        if let data = string.data(using: .utf8) {
            append(data)
        }
    }
}
