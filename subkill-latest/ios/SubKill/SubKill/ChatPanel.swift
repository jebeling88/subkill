import SwiftUI
import UIKit

struct ChatPanel: View {
    @EnvironmentObject var store: AppStore
    @State private var draft = ""
    @FocusState private var focused: Bool

    private let suggestions = ["What's costing me the most?", "Which ones am I not using?", "Help me kill the most expensive one"]

    var body: some View {
        VStack(spacing: 0) {
            Divider()
            header
            if store.chatExpanded {
                transcript
                    .frame(height: 320)
            } else if store.messages.isEmpty {
                suggestionRow
            }
            composer
        }
        .background(.regularMaterial)
    }

    private var header: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.2)) { store.chatExpanded.toggle() }
            if !store.chatExpanded { focused = false }
        } label: {
            HStack {
                Image(systemName: "sparkles")
                Text("Ask Claude to kill something").font(.footnote.weight(.semibold))
                Spacer()
                Image(systemName: store.chatExpanded ? "chevron.down" : "chevron.up")
            }
            .foregroundStyle(.secondary)
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
        }
        .buttonStyle(.plain)
    }

    private var suggestionRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(suggestions, id: \.self) { s in
                    Button(s) { Task { await store.send(s) } }
                        .font(.footnote)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.secondary.opacity(0.15))
                        .clipShape(Capsule())
                        .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
        }
        .padding(.bottom, 6)
    }

    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    if store.messages.isEmpty {
                        Text("Tell me what to cancel, or ask what's draining your account.")
                            .font(.footnote).foregroundStyle(.secondary).padding(.top, 8)
                        suggestionRow.padding(.horizontal, -16)
                    }
                    ForEach(store.messages) { m in
                        MessageView(message: m)
                    }
                    if store.sending {
                        HStack(spacing: 8) { ProgressView(); Text("Thinking…").font(.footnote).foregroundStyle(.secondary) }
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
            }
            .onChange(of: store.messages.count) { _, _ in
                withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
            }
            .onChange(of: store.sending) { _, _ in
                withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
            }
        }
    }

    private var composer: some View {
        HStack(alignment: .bottom, spacing: 8) {
            TextField("Cancel Netflix…", text: $draft, axis: .vertical)
                .lineLimit(1...3)
                .focused($focused)
                .padding(.horizontal, 12)
                .padding(.vertical, 9)
                .background(Color(.secondarySystemBackground))
                .clipShape(RoundedRectangle(cornerRadius: 18))
                .submitLabel(.send)
                .onSubmit(submit)
            Button(action: submit) {
                Image(systemName: "arrow.up.circle.fill").font(.system(size: 32))
            }
            .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || store.sending)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .onChange(of: focused) { _, isFocused in
            if isFocused { withAnimation { store.chatExpanded = true } }
        }
    }

    private func submit() {
        let t = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty, !store.sending else { return }
        draft = ""
        Task { await store.send(t) }
    }
}

struct MessageView: View {
    let message: ChatMessage

    var body: some View {
        VStack(alignment: message.role == "user" ? .trailing : .leading, spacing: 8) {
            Text(message.text)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(message.role == "user" ? Color.accentColor : Color(.secondarySystemBackground))
                .foregroundStyle(message.role == "user" ? Color.white : Color.primary)
                .clipShape(RoundedRectangle(cornerRadius: 16))
                .frame(maxWidth: .infinity, alignment: message.role == "user" ? .trailing : .leading)
            ForEach(Array(message.actions.enumerated()), id: \.offset) { _, action in
                if action.type == "cancel_plan" {
                    PlanCard(action: action)
                }
            }
        }
    }
}

struct PlanCard: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.openURL) private var openURL
    let action: ChatAction
    @State private var copied = false

    private var id: Int { action.subscriptionId ?? 0 }
    private var plan: CancelPlan? { action.plan }
    private var cancelURL: URL? {
        guard let s = plan?.cancelUrl, s.hasPrefix("https://") else { return nil }
        return URL(string: s)
    }
    private var done: Bool { store.cancelledIDs.contains(id) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Cancel \(action.merchant ?? "subscription")").font(.headline)
                Spacer()
                if let c = action.monthlyCents {
                    Text("\(Fmt.money(c))/mo").font(.subheadline).foregroundStyle(.secondary)
                }
            }
            HStack(spacing: 6) {
                if let m = plan?.method { Pill(text: m) }
                if let d = plan?.difficulty { Pill(text: d, color: d == "easy" ? .green : (d == "hard" ? .red : .orange)) }
            }
            if let cav = plan?.caveats, !cav.isEmpty {
                Text(cav).font(.footnote).foregroundStyle(.secondary)
            }
            ForEach(Array((plan?.steps ?? []).enumerated()), id: \.offset) { i, step in
                Text("\(i + 1). \(step)").font(.footnote)
            }
            HStack(spacing: 8) {
                if let url = cancelURL {
                    Button("Open cancel page") {
                        openURL(url)
                        Task { await store.markCancelling(id) }
                    }
                    .buttonStyle(.borderedProminent).tint(.red)
                }
                if let emailBody = plan?.emailBody, !emailBody.isEmpty {
                    Button(copied ? "Copied" : "Copy email") {
                        let to = plan?.contactEmail ?? ""
                        UIPasteboard.general.string = "To: \(to)\nSubject: \(plan?.emailSubject ?? "")\n\n\(emailBody)"
                        copied = true
                    }
                    .buttonStyle(.bordered)
                }
            }
            .controlSize(.small)
            if done {
                Label("Marked as killed. I'll watch for rogue charges.", systemImage: "checkmark.circle.fill")
                    .font(.footnote).foregroundStyle(.green)
            } else {
                Button("✓ I cancelled it") { Task { await store.confirmCancelled(id) } }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
            }
        }
        .padding(12)
        .background(Color(.systemBackground))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.secondary.opacity(0.25)))
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}
