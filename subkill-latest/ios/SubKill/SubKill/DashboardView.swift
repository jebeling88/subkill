import SwiftUI

struct DashboardView: View {
    @EnvironmentObject var store: AppStore
    @State private var showAdd = false
    @State private var confirmDelete = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                content
                ChatPanel()
            }
            .navigationTitle("SubKill")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Menu {
                        Picker("Sort by", selection: $store.sortMode) {
                            ForEach(SortMode.allCases) { Text($0.rawValue).tag($0) }
                        }
                    } label: {
                        Label(store.sortMode.rawValue, systemImage: "arrow.up.arrow.down")
                            .font(.footnote)
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button { showAdd = true } label: { Label("Add subscriptions", systemImage: "plus") }
                        if let url = store.privacyURL {
                            Link(destination: url) { Label("Privacy policy", systemImage: "hand.raised") }
                        }
                        Button { store.logout() } label: {
                            Label("Sign out", systemImage: "rectangle.portrait.and.arrow.right")
                        }
                        Button(role: .destructive) { confirmDelete = true } label: {
                            Label("Delete account", systemImage: "trash")
                        }
                    } label: {
                        Image(systemName: "plus.circle.fill")
                    }
                }
            }
            .sheet(isPresented: $showAdd) { AddSheet() }
            .confirmationDialog("Delete your account and all your subscription data? This can't be undone.",
                                isPresented: $confirmDelete, titleVisibility: .visible) {
                Button("Delete account", role: .destructive) { Task { await store.deleteAccount() } }
                Button("Cancel", role: .cancel) {}
            }
        }
    }

    @ViewBuilder private var content: some View {
        List {
            if let s = store.summary {
                SummaryHeader(summary: s)
                    .listRowSeparator(.hidden)
                    .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 4, trailing: 16))
            }
            if let b = store.banner {
                Text(b).font(.footnote).foregroundStyle(.red)
            }
            if store.subs.isEmpty && !store.loading {
                VStack(spacing: 10) {
                    Text("Nothing here yet").font(.headline)
                    Text("Add your emails or a bank statement and Claude will dig out every recurring charge.")
                        .font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center)
                    Button("Add subscriptions") { showAdd = true }.buttonStyle(.borderedProminent)
                    Button("Load sample data") { Task { await store.seedDemo() } }
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 24)
                .listRowSeparator(.hidden)
            }
            ForEach(store.sortedSubs) { sub in
                SubscriptionRow(sub: sub)
                    .swipeActions(edge: .trailing) {
                        Button("Kill") { store.startKill(sub) }.tint(.red)
                    }
            }
        }
        .listStyle(.plain)
        .refreshable { await store.refresh() }
    }
}

struct SummaryHeader: View {
    let summary: Summary

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text(Fmt.money(summary.monthlyCents))
                    .font(.system(size: 36, weight: .bold))
                    .foregroundStyle(.red)
                Text("/ month").foregroundStyle(.secondary)
            }
            Text("\(Fmt.money0(summary.yearlyCents)) a year · \(summary.liveCount) still active")
                .font(.subheadline).foregroundStyle(.secondary)
            if summary.unusedCount > 0 {
                Text("\(summary.unusedCount) unused for 60+ days (\(Fmt.money0(summary.unusedMonthlyCents))/mo)")
                    .font(.footnote).foregroundStyle(.orange)
            }
            if summary.stillCharging > 0 {
                Text("⚠️ \(summary.stillCharging) charged you after you cancelled")
                    .font(.footnote.bold()).foregroundStyle(.red)
            }
            if summary.savedYearlyCents > 0 {
                Text("\(Fmt.money0(summary.savedYearlyCents)) a year saved so far")
                    .font(.footnote).foregroundStyle(.green)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct SubscriptionRow: View {
    @EnvironmentObject var store: AppStore
    let sub: Subscription

    private var unusedLong: Bool {
        guard let d = Fmt.days(from: sub.lastUsedAt) else { return true }
        return d > 60
    }

    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color(hue: avatarHue, saturation: 0.55, brightness: 0.7))
                Text(String(sub.merchant.prefix(1)).uppercased())
                    .font(.headline).foregroundStyle(.white)
            }
            .frame(width: 40, height: 40)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(sub.merchant).font(.body.weight(.semibold)).lineLimit(1)
                    if sub.stillCharging > 0 { Pill(text: "Still charging!", color: .red) }
                    else if sub.status == "cancelling" { Pill(text: "Cancelling", color: .orange) }
                    else if sub.status == "trial" { Pill(text: "Trial", color: .orange) }
                }
                Text(subline)
                    .font(.caption)
                    .foregroundStyle(unusedLong ? Color.orange : Color.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 4)
            VStack(alignment: .trailing, spacing: 2) {
                Text(sub.cycle == "monthly" ? Fmt.money(sub.amountCents, sub.currency)
                                            : "≈ \(Fmt.money(sub.monthlyCents, sub.currency))")
                    .font(.body.weight(.bold))
                Text(sub.cycle == "monthly" ? "per month"
                                            : "\(Fmt.money(sub.amountCents, sub.currency))/\(shortCycle)")
                    .font(.caption2).foregroundStyle(.secondary)
            }
            Button("Kill") { store.startKill(sub) }
                .buttonStyle(.borderedProminent)
                .tint(.red)
                .controlSize(.small)
        }
        .padding(.vertical, 4)
    }

    // Stable across launches (String.hashValue is randomized per launch).
    private var avatarHue: Double {
        let h = sub.merchant.unicodeScalars.reduce(7) { (acc: Int, c: Unicode.Scalar) -> Int in
            (acc &* 31 &+ Int(c.value)) % 360
        }
        return Double(h) / 360.0
    }

    private var shortCycle: String {
        switch sub.cycle {
        case "weekly": return "wk"
        case "quarterly": return "qtr"
        case "yearly": return "yr"
        default: return "mo"
        }
    }

    private var subline: String {
        var parts: [String] = []
        if let o = sub.owner, !o.isEmpty { parts.append(o) }
        if let used = Fmt.ago(sub.lastUsedAt) { parts.append("used \(used)") } else { parts.append("no use seen") }
        if let r = Fmt.renews(sub.nextRenewal) { parts.append(r) }
        return parts.joined(separator: " · ")
    }
}

struct Pill: View {
    let text: String
    var color: Color = .gray
    var body: some View {
        Text(text)
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 7)
            .padding(.vertical, 2)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }
}
