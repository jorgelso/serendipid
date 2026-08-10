// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "SuperBrainCore",
    platforms: [
        .iOS(.v17),
        .macOS(.v14)
    ],
    products: [
        .library(
            name: "SuperBrainCore",
            targets: ["SuperBrainCore"]
        )
    ],
    targets: [
        .target(
            name: "SuperBrainCore",
            resources: [
                .process("Resources/Colors.xcassets")
            ]
        ),
        .testTarget(
            name: "SuperBrainCoreTests",
            dependencies: ["SuperBrainCore"]
        )
    ]
)
