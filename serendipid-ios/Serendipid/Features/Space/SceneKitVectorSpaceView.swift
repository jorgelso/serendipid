import SwiftUI
import SceneKit
import SerendipidCore

/// The Space tab's 3D scene — an `SCNView` wrapped for SwiftUI. Deliberately
/// SceneKit rather than RealityKit: RealityKit's SwiftUI-native `RealityView`
/// needs iOS 18+, and this app targets iOS 17. `allowsCameraControl = true`
/// gives free orbit/pan/pinch-zoom with no custom camera rig, which is the
/// whole reason to reach for SceneKit here — plain `SCNSphere` nodes (one per
/// point) are trivially fast at the few-hundred-point scale this app runs at,
/// no instancing needed.
///
/// The scene always renders on a fixed dark "space" canvas regardless of the
/// app's light/dark appearance (`vizSeriesHexDark` is the palette designed
/// for contrast against a dark background) — a data-viz canvas like this one
/// doesn't need to track system appearance the way normal UI chrome does.
struct SceneKitVectorSpaceView: UIViewRepresentable {
    let points: [VectorSpacePoint]
    let resetSignal: Int
    /// nil = every point at full brightness. Non-nil = only points whose
    /// shortcode is in the set stay bright; everything else dims via
    /// `SCNNode.opacity` rather than being removed from the scene, so
    /// spatial context (where the highlighted points sit relative to the
    /// rest of the cloud) is preserved. Fed by either a legend tap or a
    /// search match set — see `SpaceViewModel.highlightedShortcodes`.
    let highlightedShortcodes: Set<String>?
    let onSelect: (VectorSpacePoint) -> Void

    private static let backgroundColor = UIColor(red: 0.035, green: 0.043, blue: 0.078, alpha: 1)
    private static let initialCameraTransform = SCNMatrix4MakeTranslation(0, 0, 52)
    private static let sphereRadius: CGFloat = 0.4
    private static let dimmedOpacity: CGFloat = 0.12
    private static let axisNodeNamePrefix = "axis-"

    func makeUIView(context: Context) -> SCNView {
        let view = SCNView()
        view.scene = Self.buildScene(points: points)
        view.backgroundColor = Self.backgroundColor
        view.allowsCameraControl = true
        view.autoenablesDefaultLighting = true
        view.antialiasingMode = .multisampling4X
        view.rendersContinuously = false

        let tapRecognizer = UITapGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.handleTap(_:)))
        view.addGestureRecognizer(tapRecognizer)
        context.coordinator.scnView = view

        return view
    }

    func updateUIView(_ uiView: SCNView, context: Context) {
        context.coordinator.onSelect = onSelect

        if context.coordinator.lastPoints != points {
            uiView.scene = Self.buildScene(points: points)
            context.coordinator.lastPoints = points
            context.coordinator.pointsByShortcode = Dictionary(uniqueKeysWithValues: points.map { ($0.shortcode, $0) })
            context.coordinator.lastHighlightedShortcodes = nil // force a fresh opacity pass below
        }

        if context.coordinator.lastResetSignal != resetSignal {
            uiView.pointOfView?.transform = Self.initialCameraTransform
            context.coordinator.lastResetSignal = resetSignal
        }

        if context.coordinator.lastHighlightedShortcodes != highlightedShortcodes {
            Self.applyHighlight(highlightedShortcodes, to: uiView.scene, pointsByShortcode: context.coordinator.pointsByShortcode)
            context.coordinator.lastHighlightedShortcodes = highlightedShortcodes
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(onSelect: onSelect, points: points, resetSignal: resetSignal, highlightedShortcodes: highlightedShortcodes)
    }

    /// Dims every point node not in `shortcodes` (leaves axis nodes — tagged
    /// with `axisNodeNamePrefix` — untouched); `shortcodes == nil` restores
    /// full brightness for everything.
    private static func applyHighlight(_ shortcodes: Set<String>?, to scene: SCNScene?, pointsByShortcode: [String: VectorSpacePoint]) {
        guard let scene else { return }
        for node in scene.rootNode.childNodes {
            guard let name = node.name, !name.hasPrefix(axisNodeNamePrefix) else { continue }
            guard pointsByShortcode[name] != nil else { continue }
            node.opacity = (shortcodes == nil || shortcodes!.contains(name)) ? 1.0 : dimmedOpacity
        }
    }

    private static func buildScene(points: [VectorSpacePoint]) -> SCNScene {
        let scene = SCNScene()

        for point in points {
            let sphere = SCNSphere(radius: sphereRadius)
            sphere.segmentCount = 14

            let material = SCNMaterial()
            // `.constant` ignores scene lighting and always shows the exact
            // diffuse color — reliable, vivid marks for a categorical scatter
            // regardless of camera angle or light placement, same rationale
            // as an unlit/emissive material in other 3D-scatter tools.
            material.lightingModel = .constant
            material.diffuse.contents = UIColor(SpacePalette.color(for: point.colorSlot))
            sphere.materials = [material]

            let node = SCNNode(geometry: sphere)
            node.position = SCNVector3(point.position.x, point.position.y, point.position.z)
            node.name = point.shortcode
            scene.rootNode.addChildNode(node)
        }

        let maxExtent = points.reduce(into: Float(0)) { result, point in
            result = max(result, abs(point.position.x), abs(point.position.y), abs(point.position.z))
        }
        addAxes(to: scene, halfLength: max(maxExtent * 1.15, 5))

        let cameraNode = SCNNode()
        cameraNode.camera = SCNCamera()
        cameraNode.camera?.zFar = 500
        cameraNode.transform = initialCameraTransform
        scene.rootNode.addChildNode(cameraNode)

        return scene
    }

    /// Standard red/green/blue X/Y/Z convention (matches Blender, Unity, most
    /// 3D tools) rather than the app's brand palette — these are a technical
    /// reference overlay, not categorical data, so borrowing a universally
    /// recognized convention beats inventing a new one.
    private static func addAxes(to scene: SCNScene, halfLength: Float) {
        let axes: [(name: String, direction: SCNVector3, color: UIColor, label: String)] = [
            ("axis-x", SCNVector3(1, 0, 0), UIColor(red: 0.95, green: 0.29, blue: 0.29, alpha: 1), "X"),
            ("axis-y", SCNVector3(0, 1, 0), UIColor(red: 0.30, green: 0.85, blue: 0.45, alpha: 1), "Y"),
            ("axis-z", SCNVector3(0, 0, 1), UIColor(red: 0.35, green: 0.55, blue: 0.98, alpha: 1), "Z"),
        ]

        for axis in axes {
            let line = SCNCylinder(radius: 0.035, height: CGFloat(halfLength * 2))
            let material = SCNMaterial()
            material.lightingModel = .constant
            material.diffuse.contents = axis.color.withAlphaComponent(0.55)
            line.materials = [material]

            let lineNode = SCNNode(geometry: line)
            lineNode.name = axis.name
            // SCNCylinder's long axis is +Y by default; rotate it onto the
            // target axis direction, then center it on the origin.
            if axis.direction.x == 1 {
                lineNode.eulerAngles = SCNVector3(0, 0, Float.pi / 2)
            } else if axis.direction.z == 1 {
                lineNode.eulerAngles = SCNVector3(Float.pi / 2, 0, 0)
            }
            scene.rootNode.addChildNode(lineNode)

            let labelText = SCNText(string: axis.label, extrusionDepth: 0.4)
            labelText.font = .systemFont(ofSize: 6, weight: .bold)
            let labelMaterial = SCNMaterial()
            labelMaterial.lightingModel = .constant
            labelMaterial.diffuse.contents = axis.color
            labelText.materials = [labelMaterial]

            let labelNode = SCNNode(geometry: labelText)
            labelNode.name = "\(axis.name)-label"
            labelNode.scale = SCNVector3(0.08, 0.08, 0.08)
            let tip = axis.direction
            labelNode.position = SCNVector3(
                tip.x * (halfLength + 1.5),
                tip.y * (halfLength + 1.5),
                tip.z * (halfLength + 1.5)
            )
            // Always face the camera regardless of orbit angle, since text
            // extruded into 3D would otherwise read backwards/edge-on from
            // most viewing angles.
            labelNode.constraints = [SCNBillboardConstraint()]
            scene.rootNode.addChildNode(labelNode)
        }
    }

    @MainActor
    final class Coordinator: NSObject {
        var onSelect: (VectorSpacePoint) -> Void
        var lastPoints: [VectorSpacePoint]
        var lastResetSignal: Int
        var lastHighlightedShortcodes: Set<String>?
        var pointsByShortcode: [String: VectorSpacePoint]
        weak var scnView: SCNView?

        init(onSelect: @escaping (VectorSpacePoint) -> Void, points: [VectorSpacePoint], resetSignal: Int, highlightedShortcodes: Set<String>?) {
            self.onSelect = onSelect
            self.lastPoints = points
            self.lastResetSignal = resetSignal
            self.lastHighlightedShortcodes = highlightedShortcodes
            self.pointsByShortcode = Dictionary(uniqueKeysWithValues: points.map { ($0.shortcode, $0) })
        }

        @objc func handleTap(_ gesture: UITapGestureRecognizer) {
            guard let scnView else { return }
            let location = gesture.location(in: scnView)
            let hits = scnView.hitTest(location, options: [.searchMode: SCNHitTestSearchMode.closest.rawValue])
            guard let shortcode = hits.first?.node.name, let point = pointsByShortcode[shortcode] else { return }
            onSelect(point)
        }
    }
}

/// The Space tab's fixed categorical palette — `vizSeriesHexDark` (designed
/// for contrast against a dark canvas, which the 3D scene always uses
/// regardless of the app's own light/dark appearance) plus `inkMuted` for
/// "other"/"unclustered". Shared between the SceneKit sphere materials and
/// the SwiftUI legend dots so both always agree.
enum SpacePalette {
    static func color(for slot: VectorSpaceColorSlot) -> Color {
        switch slot {
        case .theme(let index):
            guard index >= 0, index < BrightPulse.vizSeriesHexDark.count,
                  let color = Color(hex: BrightPulse.vizSeriesHexDark[index]) else {
                return BrightPulse.inkMuted
            }
            return color
        case .other, .unclustered:
            return BrightPulse.inkMuted
        }
    }
}

extension Color {
    /// Parses a `"#rrggbb"`/`"rrggbb"` hex string — `BrightPulse.vizSeriesHexLight/Dark`
    /// are raw hex (not Color Set assets), so this is the one place that
    /// needs to bridge them into SwiftUI/UIKit colors.
    init?(hex: String) {
        var hexString = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        if hexString.hasPrefix("#") { hexString.removeFirst() }
        guard hexString.count == 6, let value = UInt32(hexString, radix: 16) else { return nil }
        let red = Double((value >> 16) & 0xFF) / 255
        let green = Double((value >> 8) & 0xFF) / 255
        let blue = Double(value & 0xFF) / 255
        self.init(red: red, green: green, blue: blue)
    }
}
