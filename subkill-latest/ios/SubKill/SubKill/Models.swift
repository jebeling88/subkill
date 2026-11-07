import Foundation

struct Subscription: Identifiable, Codable, Hashable {
    let id: Int
    let merchant: String
    let plan: String?
    let amountCents: Int
    let currency: String
    let cycle: String
    let monthlyCents: Int
    let category: String?
    let owner: String?
    let status: String
    let startedAt: String?
    let lastUsedAt: String?
    let nextRenewal: String?
    let useCount: Int
    let stillCharging: Int
}

struct Summary: Codable {
    let liveCount: Int
    let monthlyCents: Int
    let yearlyCents: Int
    let unusedCount: Int
    let unusedMonthlyCents: Int
    let renewingSoon: Int
    let savedYearlyCents: Int
    let cancelledCount: Int
    let stillCharging: Int
}

struct CancelPlan: Codable {
    let method: String?
    let difficulty: String?
    let cancelUrl: String?
    let steps: [String]?
    let contactEmail: String?
    let emailSubject: String?
    let emailBody: String?
    let caveats: String?
}

struct ChatAction: Codable {
    let type: String
    let subscriptionId: Int?
    let merchant: String?
    let monthlyCents: Int?
    let plan: CancelPlan?
}

struct ChatResponse: Codable {
    let reply: String
    let actions: [ChatAction]
}

struct LoginResponse: Codable { let token: String }
struct IngestResult: Codable { let found: Int; let new: Int; let updated: Int }
struct Empty: Codable {}

struct ChatMessage: Identifiable {
    let id = UUID()
    let role: String          // "user" or "assistant"
    var text: String
    var actions: [ChatAction] = []
}

enum SortMode: String, CaseIterable, Identifiable {
    case cost = "Most expensive"
    case unused = "Longest unused"
    case mostUsed = "Most used"
    case oldest = "Oldest"
    case renewal = "Renews soonest"
    var id: String { rawValue }
}

enum Fmt {
    static func money(_ cents: Int, _ currency: String = "USD") -> String {
        let f = NumberFormatter()
        f.numberStyle = .currency
        f.currencyCode = currency
        return f.string(from: NSNumber(value: Double(cents) / 100)) ?? "$\(cents / 100)"
    }
    static func money0(_ cents: Int) -> String {
        let f = NumberFormatter()
        f.numberStyle = .currency
        f.currencyCode = "USD"
        f.maximumFractionDigits = 0
        return f.string(from: NSNumber(value: Double(cents) / 100)) ?? "$\(cents / 100)"
    }
    private static let iso: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()
    static func days(from isoDate: String?) -> Int? {
        guard let s = isoDate, s.count >= 10, let d = iso.date(from: String(s.prefix(10))) else { return nil }
        return Calendar.current.dateComponents([.day], from: d, to: Date()).day
    }
    static func ago(_ isoDate: String?) -> String? {
        guard let n = days(from: isoDate) else { return nil }
        if n <= 0 { return "today" }
        if n == 1 { return "yesterday" }
        if n < 60 { return "\(n)d ago" }
        if n < 700 { return "\(n / 30) mo ago" }
        return "\(n / 365)y ago"
    }
    static func renews(_ isoDate: String?) -> String? {
        guard let n = days(from: isoDate) else { return nil }
        let left = -n
        if left < 0 { return nil }
        if left == 0 { return "renews today" }
        if left == 1 { return "renews tomorrow" }
        return "renews in \(left)d"
    }
}
