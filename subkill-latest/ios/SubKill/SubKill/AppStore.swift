import Foundation
import SwiftUI

@MainActor
final class AppStore: ObservableObject {
    @Published var loggedIn = false
    @Published var loading = false
    @Published var subs: [Subscription] = []
    @Published var summary: Summary?
    @Published var sortMode: SortMode = .cost
    @Published var messages: [ChatMessage] = []
    @Published var sending = false
    @Published var chatExpanded = false
    @Published var banner: String?
    @Published var cancelledIDs: Set<Int> = []
    @Published var serverURL: String

    private let api: APIClient

    init() {
        let url = UserDefaults.standard.string(forKey: "serverURL") ?? Config.defaultServer
        serverURL = url
        api = APIClient(baseURL: url, token: Keychain.load("token"))
        loggedIn = api.token != nil
        if loggedIn { Task { await refresh() } }
    }

    var sortedSubs: [Subscription] {
        switch sortMode {
        case .cost:
            return subs.sorted { $0.monthlyCents > $1.monthlyCents }
        case .unused:
            return subs.sorted {
                let a = $0.lastUsedAt ?? "", b = $1.lastUsedAt ?? ""
                return a == b ? $0.monthlyCents > $1.monthlyCents : a < b
            }
        case .mostUsed:
            return subs.sorted { $0.useCount > $1.useCount }
        case .oldest:
            return subs.sorted { ($0.startedAt ?? "9999") < ($1.startedAt ?? "9999") }
        case .renewal:
            return subs.sorted { ($0.nextRenewal ?? "9999") < ($1.nextRenewal ?? "9999") }
        }
    }

    // MARK: auth
    func login(email: String, password: String, signup: Bool, server: String, invite: String = "") async -> String? {
        let clean = server.trimmingCharacters(in: .whitespacesAndNewlines)
        api.baseURL = clean
        serverURL = clean
        UserDefaults.standard.set(clean, forKey: "serverURL")
        do {
            var body: [String: Any] = ["email": email, "password": password]
            if signup { body["invite"] = invite }
            let r: LoginResponse = try await api.call(signup ? "/api/signup" : "/api/login",
                                                      method: "POST", body: body)
            api.token = r.token
            Keychain.save(r.token, for: "token")
            loggedIn = true
            await refresh()
            return nil
        } catch {
            return error.localizedDescription
        }
    }

    func logout() {
        if let old = api.token {
            let temp = APIClient(baseURL: api.baseURL, token: old)
            Task { try? await temp.send("/api/logout") }
        }
        api.token = nil
        Keychain.delete("token")
        loggedIn = false
        subs = []
        summary = nil
        messages = []
        cancelledIDs = []
    }

    /// Apple requires in-app account deletion: wipes the account on the server, then signs out.
    func deleteAccount() async {
        do {
            try await api.send("/api/account", method: "DELETE")
            logout()
        } catch {
            banner = error.localizedDescription
        }
    }

    var privacyURL: URL? { URL(string: serverURL.trimmingCharacters(in: CharacterSet(charactersIn: "/ ")) + "/privacy") }

    // MARK: data
    func refresh() async {
        loading = true
        defer { loading = false }
        do {
            let list: [Subscription] = try await api.call("/api/subscriptions?status=live&sort=cost")
            let sum: Summary = try await api.call("/api/summary")
            subs = list
            summary = sum
            banner = nil
        } catch let e as APIError {
            if e.unauthorized { logout() } else { banner = e.message }
        } catch {
            banner = error.localizedDescription
        }
    }

    func seedDemo() async {
        try? await api.send("/api/demo/seed")
        await refresh()
    }

    func ingest(_ text: String) async throws -> IngestResult {
        let r: IngestResult = try await api.call("/api/ingest/text", method: "POST",
                                                 body: ["text": text, "kind": "email"], timeout: 120)
        await refresh()
        return r
    }

    // MARK: kill flow
    func startKill(_ s: Subscription) {
        Task { await send("Help me cancel \(s.merchant) (\(Fmt.money(s.monthlyCents, s.currency))/mo).") }
    }

    func markCancelling(_ id: Int) async {
        try? await api.send("/api/subscriptions/\(id)/mark-cancelling")
        await refresh()
    }

    func confirmCancelled(_ id: Int) async {
        do {
            try await api.send("/api/subscriptions/\(id)/mark-cancelled")
            cancelledIDs.insert(id)
            await refresh()
        } catch {
            banner = error.localizedDescription
        }
    }

    // MARK: chat
    func send(_ text: String) async {
        guard !sending else { return }
        chatExpanded = true
        messages.append(ChatMessage(role: "user", text: text))
        sending = true
        defer { sending = false }
        let history: [[String: String]] = messages.suffix(20).map { ["role": $0.role, "content": $0.text] }
        do {
            let r: ChatResponse = try await api.call("/api/chat", method: "POST",
                                                     body: ["messages": history], timeout: 120)
            messages.append(ChatMessage(role: "assistant", text: r.reply, actions: r.actions))
            if !r.actions.isEmpty { await refresh() }
        } catch let e as APIError {
            if e.unauthorized { logout() }
            else { messages.append(ChatMessage(role: "assistant", text: "⚠️ \(e.message)")) }
        } catch {
            messages.append(ChatMessage(role: "assistant", text: "⚠️ \(error.localizedDescription)"))
        }
    }
}
