import Foundation
import Security

struct APIError: LocalizedError {
    let message: String
    var unauthorized = false
    var errorDescription: String? { message }
}

enum Keychain {
    static func save(_ value: String, for key: String) {
        let base: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                   kSecAttrAccount as String: key]
        SecItemDelete(base as CFDictionary)
        var add = base
        add[kSecValueData as String] = Data(value.utf8)
        SecItemAdd(add as CFDictionary, nil)
    }
    static func load(_ key: String) -> String? {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                kSecAttrAccount as String: key,
                                kSecReturnData as String: true,
                                kSecMatchLimit as String: kSecMatchLimitOne]
        var out: AnyObject?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess,
              let data = out as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
    static func delete(_ key: String) {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                kSecAttrAccount as String: key]
        SecItemDelete(q as CFDictionary)
    }
}

final class APIClient {
    var baseURL: String
    var token: String?

    init(baseURL: String, token: String?) {
        self.baseURL = baseURL
        self.token = token
    }

    private func raw(_ path: String, method: String, body: [String: Any]?, timeout: TimeInterval) async throws -> Data {
        let base = baseURL.trimmingCharacters(in: CharacterSet(charactersIn: "/ "))
        guard let url = URL(string: base + path) else { throw APIError(message: "That server address doesn't look right.") }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.timeoutInterval = timeout
        req.setValue("1", forHTTPHeaderField: "X-SubKill")
        if let token = token { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let body = body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let data: Data
        let resp: URLResponse
        do {
            (data, resp) = try await URLSession.shared.data(for: req)
        } catch {
            throw APIError(message: "Can't reach the server. Is it running, and is the address right?")
        }
        guard let http = resp as? HTTPURLResponse else { throw APIError(message: "No response from the server.") }
        if !(200..<300).contains(http.statusCode) {
            var msg = "Something went wrong (\(http.statusCode))."
            if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let detail = obj["detail"] as? String { msg = detail }
            throw APIError(message: msg, unauthorized: http.statusCode == 401 && path != "/api/login")
        }
        return data
    }

    func call<T: Decodable>(_ path: String, method: String = "GET", body: [String: Any]? = nil,
                            timeout: TimeInterval = 30) async throws -> T {
        let data = try await raw(path, method: method, body: body, timeout: timeout)
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        do { return try dec.decode(T.self, from: data) }
        catch { throw APIError(message: "The server sent something unexpected.") }
    }

    func send(_ path: String, method: String = "POST", body: [String: Any]? = nil) async throws {
        _ = try await raw(path, method: method, body: body, timeout: 30)
    }
}
