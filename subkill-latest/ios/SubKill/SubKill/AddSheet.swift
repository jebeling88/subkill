import SwiftUI

struct AddSheet: View {
    @EnvironmentObject var store: AppStore
    @Environment(\.dismiss) private var dismiss
    @State private var text = ""
    @State private var busy = false
    @State private var message: String?

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 12) {
                Text("Paste receipts, renewal emails or bank statement lines. Claude pulls out the recurring ones.")
                    .font(.footnote).foregroundStyle(.secondary)
                TextEditor(text: $text)
                    .frame(minHeight: 180)
                    .padding(6)
                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.secondary.opacity(0.3)))
                if let m = message { Text(m).font(.footnote) }
                Button {
                    Task {
                        busy = true
                        do {
                            let r = try await store.ingest(text)
                            message = "Found \(r.found): \(r.new) new, \(r.updated) updated."
                            text = ""
                        } catch { message = error.localizedDescription }
                        busy = false
                    }
                } label: {
                    Text(busy ? "Claude is reading…" : "Find subscriptions").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .disabled(busy || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                Divider()
                Button("Load sample data instead") {
                    Task { await store.seedDemo(); dismiss() }
                }
                .font(.footnote)
                Spacer()
            }
            .padding()
            .navigationTitle("Add subscriptions")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
        }
    }
}
