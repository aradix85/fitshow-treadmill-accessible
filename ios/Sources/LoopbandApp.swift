import SwiftUI

@main
struct LoopbandApp: App {
    @StateObject private var treadmill = Treadmill.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(treadmill)
        }
    }
}
