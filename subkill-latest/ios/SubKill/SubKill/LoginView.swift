import SwiftUI

struct LoginView: View {
    @EnvironmentObject var store: AppStore
    @State private var server = ""
    @State private var email = ""
    @State private var password = ""
    @State private var invite = ""
    @State private var signup = false
    @State private var error: String?
    @State private var busy = false

    var body: some View {
        VStack(spacing: 14) {
            Spacer()
            Text("SubKill")
                .font(.system(size: 38, weight: .bold))
            Text("Every forgotten subscription, ranked by what it costs you.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.bottom, 8)

            TextField("Email", text: $email)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .keyboardType(.emailAddress)
                .textContentType(.username)
                .textFieldStyle(.roundedBorder)
            SecureField("Password (8+ characters)", text: $password)
                .textContentType(signup ? .newPassword : .password)
                .textFieldStyle(.roundedBorder)

            if signup {
                TextField("Invite code", text: $invite)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .textFieldStyle(.roundedBorder)
            }

            DisclosureGroup("Advanced") {
                TextField("Server address", text: $server)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .textFieldStyle(.roundedBorder)
            }
            .font(.footnote)
            .foregroundStyle(.secondary)

            if let error = error {
                Text(error).font(.footnote).foregroundStyle(.red).multilineTextAlignment(.center)
            }

            Button {
                Task {
                    busy = true
                    error = await store.login(email: email, password: password, signup: signup, server: server, invite: invite)
                    busy = false
                }
            } label: {
                Text(busy ? "One moment…" : (signup ? "Create account" : "Sign in"))
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(busy || email.isEmpty || password.count < 8 || server.isEmpty)

            Button(signup ? "Have an account? Sign in" : "New here? Create an account") {
                signup.toggle()
            }
            .font(.footnote)
            Spacer()
            Spacer()
        }
        .padding(24)
        .onAppear { server = store.serverURL }
    }
}
