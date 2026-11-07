import SwiftUI

@main
struct SubKillApp: App {
    @StateObject private var store = AppStore()

    var body: some Scene {
        WindowGroup {
            Group {
                if store.loggedIn {
                    DashboardView()
                } else {
                    LoginView()
                }
            }
            .environmentObject(store)
        }
    }
}
