// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "SerendipidCore",
    platforms: [
        .iOS(.v17),
        .macOS(.v14)
    ],
    products: [
        .library(
            name: "SerendipidCore",
            targets: ["SerendipidCore"]
        )
    ],
    targets: [
        .target(
            name: "SerendipidCore",
            resources: [
                .process("Resources/Colors.xcassets")
            ]
        ),
        .testTarget(
            name: "SerendipidCoreTests",
            dependencies: ["SerendipidCore"]
        )
    ]
)
