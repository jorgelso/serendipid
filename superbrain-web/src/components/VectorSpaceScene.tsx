"use client";

import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { Html, Instance, Instances, Line, OrbitControls, Stars } from "@react-three/drei";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import type { VectorSpaceColorSlot, VectorSpacePoint } from "@/types/domain";
import {
  LEGEND_VISIBLE_CAP,
  colorForSlot,
  computeDualHuePairs,
  dualHueSlotsForSlot,
  seriesIndex,
  useVizPalette,
  vividColorForSlot,
} from "@/lib/useVizPalette";
import HoverPreviewCard from "./HoverPreviewCard";

interface VectorSpaceSceneProps {
  points: VectorSpacePoint[];
  // Shortcodes to keep at full brightness; everything else dims to neutral
  // gray. null means "no filter, show everything at full brightness" — one
  // mechanism serves both the legend's per-theme selection (highlighting one
  // theme's points, even themes past the 8-color cap) and the semantic
  // search box (highlighting whatever the cosine-similarity search matched),
  // since both are really the same operation: a set of shortcodes to light
  // up as if they were one cluster.
  highlightedShortcodes: Set<string> | null;
  onSelect: (shortcode: string) => void;
  // Mirrors VectorSpaceLegend's own expanded/collapsed state (owned by the
  // shared parent, VectorSpaceView) so collapsing the legend to its top-8
  // view also grays out every point past that rank, not just the rows.
  legendExpanded: boolean;
}

export interface VectorSpaceSceneHandle {
  resetCamera: () => void;
}

const DEFAULT_CAMERA_POSITION: [number, number, number] = [0, 20, 90];

// Bridges the imperative reset handle (owned by the outer, DOM-land
// component below) into the r3f tree — useThree()/the camera instance only
// exist inside <Canvas>, not in the component that renders it, so this
// registers the actual reset closure once mounted rather than trying to
// call useThree() from outside the Canvas.
function CameraController({
  controlsRef,
  registerReset,
}: {
  controlsRef: React.RefObject<OrbitControlsImpl | null>;
  registerReset: (fn: () => void) => void;
}) {
  const { camera } = useThree();

  useEffect(() => {
    registerReset(() => {
      camera.position.set(...DEFAULT_CAMERA_POSITION);
      const controls = controlsRef.current;
      if (controls) {
        controls.target.set(0, 0, 0);
        controls.update();
      }
    });
  }, [camera, controlsRef, registerReset]);

  return null;
}

// OrbitControls always rotates around `controls.target`, which starts (and,
// without this, stays forever) at the scene origin — so once you've zoomed
// into a cluster on the far side of the point cloud, dragging to rotate
// swings the whole view around a pivot far outside what's on screen instead
// of around what you're actually looking at. Retargets on every rotate-drag
// (left-button pointerdown, before OrbitControls' own drag math kicks in on
// the following pointermoves) to whatever point is currently hovered, or —
// if the cursor isn't over a point — to the spot straight ahead of the
// camera at its current distance to the old target, so an empty patch of
// space between points still gets a sensible local pivot instead of
// snapping back to the origin. Setting `target` and calling `update()`
// synchronously here doesn't move the camera (OrbitControls.update()
// recomputes its internal offset from the *current* camera position each
// call, so position is preserved — only the point it orbits around, and
// therefore its look direction, changes).
function FocusOrbit({
  controlsRef,
  hoveredPositionRef,
}: {
  controlsRef: React.RefObject<OrbitControlsImpl | null>;
  hoveredPositionRef: React.RefObject<[number, number, number] | null>;
}) {
  const { camera, gl } = useThree();

  useEffect(() => {
    const canvasEl = gl.domElement;
    const forward = new THREE.Vector3();

    const onPointerDown = (e: PointerEvent) => {
      if (e.button !== 0) return; // left-drag (or single-finger touch) only — not pan/dolly
      const controls = controlsRef.current;
      if (!controls) return;

      const hovered = hoveredPositionRef.current;
      if (hovered) {
        controls.target.set(...hovered);
      } else {
        const distance = camera.position.distanceTo(controls.target);
        camera.getWorldDirection(forward);
        controls.target.copy(camera.position).addScaledVector(forward, distance);
      }
      controls.update();
    };

    canvasEl.addEventListener("pointerdown", onPointerDown);
    return () => canvasEl.removeEventListener("pointerdown", onPointerDown);
  }, [camera, gl, controlsRef, hoveredPositionRef]);

  return null;
}

// A point is three coordinated layers, not one shaded sphere: a small
// "hot" core (lightened toward white, opaque — the interactive hit target),
// a bigger additive mid-glow in the true category color, and a soft additive
// outer bloom. Sized so the glow, not the core, dominates the silhouette —
// a flat-lit single sphere reads as "an opaque ball" no matter how large its
// halo is, since the sphere itself has zero internal falloff.
//
// The core and the outer glow are doing two different, opposed jobs, so
// they're sized on purpose to *not* match vectorSpace.ts's MIN_SEPARATION
// (2.4) the same way: CORE_RADIUS stays small so individual points inside a
// cluster stay visually distinct (and clickable) instead of fusing into one
// blob. OUTER_RADIUS is deliberately bigger than half of MIN_SEPARATION —
// once points are properly spaced out (leash-based declutter, see
// vectorSpace.ts), a small enough outer glow stops overlapping its
// same-cluster neighbors at all, and a theme reads as a scatter of
// disconnected specks instead of one cohesive shape. A generous outer glow
// re-blends those halos (additive, low opacity) into a visible cluster
// silhouette while the small core underneath still reads as separate dots
// up close. 1.4 was tried and reverted — in a large theme (250+ posts) the
// additively-blended halos of a dozen-plus overlapping neighbors saturate
// to a flat white wash, destroying exactly the per-point definition this
// whole effort is about; 1.0 (with GlowLayer's outer opacity also trimmed,
// see below) still blends into a cluster silhouette from a normal viewing
// distance without blowing out once you're close enough to a dense pocket
// to make out individual points.
const CORE_RADIUS = 0.35;
const MID_RADIUS = 0.45;
const OUTER_RADIUS = 1.0;
const HOVER_SCALE = 1.6;

const SCENE_BACKGROUND = "#050506";
const DIMMED_COLOR = "#3a3a3d";

// Matches vectorSpace.ts's TARGET_RADIUS (34) plus its declutter leash
// (MAX_DISPLACEMENT=4.5) with a bit of headroom so the bounding
// box/starfield visibly frame the point cloud instead of clipping.
const HALF_EXTENT = 48;

function lightenColor(hex: string, amount: number): string {
  return `#${new THREE.Color(hex).lerp(new THREE.Color("#ffffff"), amount).getHexString()}`;
}

function mixColor(hexA: string, hexB: string, weight: number): string {
  return `#${new THREE.Color(hexA).lerp(new THREE.Color(hexB), weight).getHexString()}`;
}

// While the legend is collapsed to its top-8 view, points ranked past that
// fall back to "other" (neutral gray) here too — collapsing the legend and
// losing a point's color are the same toggle from the user's perspective.
function effectiveSlot(slot: VectorSpaceColorSlot, legendExpanded: boolean): VectorSpaceColorSlot {
  if (legendExpanded) return slot;
  const idx = seriesIndex(slot);
  return idx !== null && idx >= LEGEND_VISIBLE_CAP ? "other" : slot;
}

// A faint wireframe box enclosing the data reads as a containment
// field/data volume.
function BoundingBox() {
  const geometry = useMemo(
    () => new THREE.EdgesGeometry(new THREE.BoxGeometry(HALF_EXTENT * 2, HALF_EXTENT * 2, HALF_EXTENT * 2)),
    []
  );
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color="#8a8a90" transparent opacity={0.25} />
    </lineSegments>
  );
}

const AXES: { dir: [number, number, number]; label: string }[] = [
  { dir: [1, 0, 0], label: "X" },
  { dir: [0, 1, 0], label: "Y" },
  { dir: [0, 0, 1], label: "Z" },
];

// Labels are plain HTML (via drei's Html, same technique as the hover card)
// rather than drei's <Text> — <Text> (troika-three-text) does async font
// loading through a worker/OffscreenCanvas, and that path reliably crashed
// the WebGL context in this environment (see git history/PR notes). Html
// sidesteps it entirely.
function Axes() {
  return (
    <>
      {AXES.map(({ dir, label }) => {
        const end: [number, number, number] = [dir[0] * HALF_EXTENT, dir[1] * HALF_EXTENT, dir[2] * HALF_EXTENT];
        const start: [number, number, number] = [-end[0], -end[1], -end[2]];
        return (
          <group key={label}>
            <Line points={[start, end]} color="white" lineWidth={1} transparent opacity={0.55} />
            <Html position={end} center style={{ pointerEvents: "none" }}>
              <span className="font-display text-sm font-semibold text-[#d9d9d9]">{label}</span>
            </Html>
          </group>
        );
      })}
    </>
  );
}

// Two layered starfields (near/bright + far/dim) for a bit of parallax
// depth. drei's Stars sizes points as `factor * 30 / distanceFromCamera`
// (see its shader) — the original radius/depth (160/100) placed stars
// 160-260 units out while the camera sits ~90 units from the data, so at a
// modest factor they rendered as barely-visible specks. Pulled the shells
// much closer (just outside the ~32-unit bounding box) and pushed factor way
// up so they're unmistakably there. Static: nothing in this scene moves on
// its own, only in response to the user's own camera controls.
function SpaceBackdrop() {
  return (
    <>
      <Stars radius={130} depth={110} count={9000} factor={5.5} saturation={0} fade speed={0.5} />
      <Stars radius={70} depth={45} count={1200} factor={8} saturation={0} fade speed={0.8} />
    </>
  );
}

// OrbitControls' built-in pan (right-drag / two-finger-drag) is easy to miss
// on a trackpad, and orbiting alone only ever spins around a fixed pivot —
// it can't get you close to a cluster that isn't near the origin. WASD/arrow
// keys translate the camera so the user can actually fly through the point
// cloud rather than just rotate around it.
function KeyboardFly({ controlsRef }: { controlsRef: React.RefObject<OrbitControlsImpl | null> }) {
  const { camera } = useThree();
  const pressed = useRef<Set<string>>(new Set());
  // Distance from camera to orbit target, captured fresh each time a flight
  // starts (not a fixed constant) — null means "not currently flying."
  const pivotDistance = useRef<number | null>(null);

  useEffect(() => {
    const down = (e: KeyboardEvent) => pressed.current.add(e.key.toLowerCase());
    const up = (e: KeyboardEvent) => pressed.current.delete(e.key.toLowerCase());
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, []);

  // Scratch vectors reused every frame — refs, not useMemo, since they're
  // mutated in place each tick (a plain memoized value isn't meant to be
  // written to after render).
  const scratch = useRef({ forward: new THREE.Vector3(), right: new THREE.Vector3(), move: new THREE.Vector3() });

  useFrame((_, delta) => {
    const keys = pressed.current;
    const controls = controlsRef.current;
    if (!controls) return;

    if (keys.size === 0) {
      // Not flying — leave the pivot exactly where it last landed, so a
      // drag-rotate right after stopping still pivots around that spot.
      // Only reset the *captured distance* so the next flight re-measures
      // from wherever the user has since zoomed/orbited to.
      pivotDistance.current = null;
      return;
    }

    const { forward, right, move } = scratch.current;
    camera.getWorldDirection(forward);
    right.crossVectors(forward, camera.up).normalize();

    if (pivotDistance.current === null) {
      pivotDistance.current = camera.position.distanceTo(controls.target);
    }

    move.set(0, 0, 0);
    if (keys.has("w") || keys.has("arrowup")) move.add(forward);
    if (keys.has("s") || keys.has("arrowdown")) move.sub(forward);
    if (keys.has("d") || keys.has("arrowright")) move.add(right);
    if (keys.has("a") || keys.has("arrowleft")) move.sub(right);
    if (keys.has(" ")) move.y += 1;
    if (keys.has("shift")) move.y -= 1;
    if (move.lengthSq() === 0) return;

    move.normalize().multiplyScalar(40 * delta);
    camera.position.add(move);
    // Pin the orbit pivot directly ahead of the camera at a fixed distance,
    // instead of translating it by the same delta as before — that kept the
    // pivot at "wherever it happened to end up," which could drift away
    // from what's actually centered in view after enough combined flying
    // and rotating. Pinning it to "straight ahead, fixed distance" means a
    // drag-rotate right after flying always pivots around whatever you're
    // actually looking at.
    controls.target.copy(camera.position).addScaledVector(forward, pivotDistance.current);
    controls.update();
  });

  return null;
}

// @react-three/fiber does not itself handle WebGL context loss (nothing in
// its source listens for `webglcontextlost`) — and per the WebGL spec, a
// lost context is only auto-restored by the browser if something calls
// `event.preventDefault()` on that event. Without this, any context loss
// (GPU driver hiccup, resource pressure, the tab being backgrounded) leaves
// the canvas permanently blank instead of recovering.
function ContextLossHandler() {
  const { gl } = useThree();

  useEffect(() => {
    const canvasEl = gl.domElement;
    const onLost = (e: Event) => {
      e.preventDefault();
      console.warn("[space] WebGL context lost — attempting automatic recovery.");
    };
    const onRestored = () => console.info("[space] WebGL context restored.");

    canvasEl.addEventListener("webglcontextlost", onLost);
    canvasEl.addEventListener("webglcontextrestored", onRestored);
    return () => {
      canvasEl.removeEventListener("webglcontextlost", onLost);
      canvasEl.removeEventListener("webglcontextrestored", onRestored);
    };
  }, [gl]);

  return null;
}

interface ColoredPoint {
  point: VectorSpacePoint;
  color: string;
  coreColor: string;
  // The slot color/coreColor were actually rendered with — may differ from
  // point.colorSlot when the legend is collapsed (effectiveSlot() falls back
  // to "other"). GlowLayer's neutral-glow check needs this, not the raw
  // point.colorSlot, so a collapsed-legend point dims its glow too.
  slot: VectorSpaceColorSlot;
}

function colorFor(isDimmed: boolean, layerColor: string): string {
  return isDimmed ? DIMMED_COLOR : layerColor;
}

interface DimState {
  dimmed: boolean;
  // 1 (untouched) unless the legend/search filter itself excludes this
  // point — hover never shrinks anything, only recolors.
  scale: number;
}

// Two independent dimming mechanisms, layered rather than one overriding
// the other:
//
// The legend/search filter (highlightedShortcodes) is a hard exclusion —
// a point outside it is grayed out AND shrunk (0.35x), and hover has no
// opinion about it at all; it stays exactly as the filter left it.
//
// Hovering is a spotlight *within* whatever's currently active (the
// filtered set, or the whole cloud when no filter is on): the hovered
// point stays full brightness, every other point still in play dims in
// color only — no shrink, since these points are still legitimately part
// of the current selection and shrinking every one of them as the cursor
// sweeps across a dense cluster just adds visual jitter on top of the
// color change, not clarity. An earlier version let hover override the
// filter outright (dimming/lighting the *entire* scene regardless of an
// active legend/search selection) — that fought the filter instead of
// working inside it.
//
// legendExpanded turns this whole gray/shrink treatment off — with the
// legend collapsed, only the top 8 themes have their own color to begin
// with, and per direct testing the "gray everything else out" spotlight
// read as actively worse there than just leaving every point's normal
// (translucent) look alone. Collapsed-legend emphasis instead comes from
// OpaqueBoostLayer painting a solid, fully-opaque highlight on top of
// whatever's active — an additive layer, not a change to how everything
// else renders.
function dimStateFor(
  shortcode: string,
  highlightedShortcodes: Set<string> | null,
  hoveredShortcode: string | null,
  legendExpanded: boolean
): DimState {
  if (!legendExpanded) return { dimmed: false, scale: 1 };
  const excludedByFilter = highlightedShortcodes !== null && !highlightedShortcodes.has(shortcode);
  if (excludedByFilter) return { dimmed: true, scale: 0.35 };
  if (hoveredShortcode !== null && shortcode !== hoveredShortcode) return { dimmed: true, scale: 1 };
  return { dimmed: false, scale: 1 };
}

// "Unclustered"/"other" points (see vectorSpace.ts) are usually most of the
// library and share one neutral gray — their glow is what actually melts
// into an indistinct mass when dense, since there's no color variation to
// tell overlapping instances apart in the first place. Real clusters stay at
// full glow so they keep popping. (Restored — density-based glow scaling
// via VectorSpacePoint.glowScale was tried and then reverted; see
// vectorSpace.ts's commented-out computeGlowScales.)
function isNeutralSlot(slot: VectorSpaceColorSlot): boolean {
  return slot === "unclustered" || slot === "other";
}

const NEUTRAL_GLOW_SCALE = 0.45;

// Purely visual, non-interactive glow ring — one instanced draw call
// regardless of point count. Rendered twice (mid + outer) around the
// interactive core below.
function GlowLayer({
  colored,
  radius,
  opacity,
  highlightedShortcodes,
  hoveredShortcode,
  legendExpanded,
}: {
  colored: ColoredPoint[];
  radius: number;
  opacity: number;
  highlightedShortcodes: Set<string> | null;
  hoveredShortcode: string | null;
  legendExpanded: boolean;
}) {
  return (
    <Instances limit={colored.length || 1} range={colored.length}>
      <sphereGeometry args={[radius, 12, 12]} />
      <meshBasicMaterial
        transparent
        opacity={opacity}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
      {colored.map(({ point, color, slot }) => {
        const dim = dimStateFor(point.shortcode, highlightedShortcodes, hoveredShortcode, legendExpanded);
        const isHovered = hoveredShortcode === point.shortcode;
        const neutralScale = isNeutralSlot(slot) ? NEUTRAL_GLOW_SCALE : 1;
        return (
          <Instance
            key={point.shortcode}
            position={point.position}
            color={colorFor(dim.dimmed, color)}
            // scale={(isHovered ? HOVER_SCALE : 1) * dim.scale * point.glowScale} // density-based glow, disabled
            scale={(isHovered ? HOVER_SCALE : 1) * dim.scale * neutralScale}
          />
        );
      })}
    </Instances>
  );
}

// The interactive "hot core" — small, lightened toward white so it reads as
// a bright light source rather than a flat opaque ball, and the one layer
// that actually handles hover/click.
function CoreLayer({
  colored,
  highlightedShortcodes,
  hoveredShortcode,
  legendExpanded,
  onHover,
  onSelect,
}: {
  colored: ColoredPoint[];
  highlightedShortcodes: Set<string> | null;
  hoveredShortcode: string | null;
  legendExpanded: boolean;
  onHover: (shortcode: string | null) => void;
  onSelect: (shortcode: string) => void;
}) {
  return (
    <Instances limit={colored.length || 1} range={colored.length}>
      <sphereGeometry args={[CORE_RADIUS, 16, 16]} />
      <meshBasicMaterial toneMapped={false} />
      {colored.map(({ point, coreColor }) => {
        const dim = dimStateFor(point.shortcode, highlightedShortcodes, hoveredShortcode, legendExpanded);
        const isHovered = hoveredShortcode === point.shortcode;
        return (
          <Instance
            key={point.shortcode}
            position={point.position}
            color={colorFor(dim.dimmed, coreColor)}
            scale={(isHovered ? HOVER_SCALE : 1) * dim.scale}
            onPointerOver={(e: ThreeEvent<PointerEvent>) => {
              e.stopPropagation();
              onHover(point.shortcode);
              document.body.style.cursor = "pointer";
            }}
            onPointerOut={(e: ThreeEvent<PointerEvent>) => {
              e.stopPropagation();
              onHover(null);
              document.body.style.cursor = "auto";
            }}
            onClick={(e: ThreeEvent<MouseEvent>) => {
              e.stopPropagation();
              onSelect(point.shortcode);
            }}
          />
        );
      })}
    </Instances>
  );
}

interface DualColoredPoint {
  point: VectorSpacePoint;
  colorA: string;
  colorB: string;
}

// Slots 8-23 (see useVizPalette's dualHueSlotsForSlot) reuse one of the 8
// base hues, so they render here as a genuine two-tone split sphere instead
// of a flat repeat of an already-used color. drei's <Instances>/<Instance>
// only carries one color per instance, so this is a raw InstancedMesh with
// a hand-populated instanceColorA/instanceColorB/instanceDim buffer —
// patched into MeshBasicMaterial's own compiled shader via onBeforeCompile
// (rather than a ShaderMaterial written from scratch) specifically so
// instancing, tone mapping, and output color space conversion all stay on
// the exact same code path every other layer in this scene already trusts;
// only diffuseColor's source is replaced.
function DualCoreLayer({
  colored,
  maxCount,
  highlightedShortcodes,
  hoveredShortcode,
  legendExpanded,
  onHover,
  onSelect,
}: {
  colored: DualColoredPoint[];
  maxCount: number;
  highlightedShortcodes: Set<string> | null;
  hoveredShortcode: string | null;
  legendExpanded: boolean;
  onHover: (shortcode: string | null) => void;
  onSelect: (shortcode: string) => void;
}) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const capacity = Math.max(maxCount, 1);

  const geometry = useMemo(() => {
    const geo = new THREE.SphereGeometry(CORE_RADIUS, 16, 16);
    geo.setAttribute("instanceColorA", new THREE.InstancedBufferAttribute(new Float32Array(capacity * 3), 3));
    geo.setAttribute("instanceColorB", new THREE.InstancedBufferAttribute(new Float32Array(capacity * 3), 3));
    geo.setAttribute("instanceDim", new THREE.InstancedBufferAttribute(new Float32Array(capacity), 1));
    return geo;
  }, [capacity]);

  const material = useMemo(() => {
    const dimmed = new THREE.Color(DIMMED_COLOR);
    const mat = new THREE.MeshBasicMaterial({ toneMapped: false });
    mat.onBeforeCompile = (shader) => {
      shader.vertexShader = shader.vertexShader
        .replace(
          "#include <common>",
          `attribute vec3 instanceColorA;
attribute vec3 instanceColorB;
attribute float instanceDim;
varying vec3 vColorA;
varying vec3 vColorB;
varying float vDim;
varying vec3 vViewOffset;
#include <common>`
        )
        .replace(
          "#include <begin_vertex>",
          `#include <begin_vertex>
vColorA = instanceColorA;
vColorB = instanceColorB;
vDim = instanceDim;
// Direction from the sphere's own center to this vertex, in camera space
// (w=0 drops translation, keeping only the instance's scale/rotation and
// the camera's own rotation) — NOT a fixed world-space axis. A fixed axis
// looks edge-on (a solid single-colored disc) from whatever viewing angle
// happens to line up with it — straight down/up, for a mostly-vertical
// axis. Splitting on camera-space X instead means the boundary is always
// perpendicular to the current view direction, so every dual-color sphere
// reads as half-and-half from any angle, orbit included.
vViewOffset = (modelViewMatrix * instanceMatrix * vec4(position, 0.0)).xyz;`
        );
      shader.fragmentShader = shader.fragmentShader
        .replace(
          "#include <common>",
          `varying vec3 vColorA;
varying vec3 vColorB;
varying float vDim;
varying vec3 vViewOffset;
#include <common>`
        )
        .replace(
          "#include <color_fragment>",
          `#include <color_fragment>
float side = normalize(vViewOffset).x;
float t = smoothstep(-0.08, 0.08, side);
vec3 splitColor = mix(vColorB, vColorA, t);
diffuseColor.rgb = mix(splitColor, vec3(${dimmed.r.toFixed(6)}, ${dimmed.g.toFixed(6)}, ${dimmed.b.toFixed(6)}), vDim);`
        );
    };
    return mat;
  }, []);

  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;

    const n = colored.length;
    mesh.count = n;

    const colorAAttr = geometry.getAttribute("instanceColorA") as THREE.InstancedBufferAttribute;
    const colorBAttr = geometry.getAttribute("instanceColorB") as THREE.InstancedBufferAttribute;
    const dimAttr = geometry.getAttribute("instanceDim") as THREE.InstancedBufferAttribute;
    const matrix = new THREE.Matrix4();
    const tmpColor = new THREE.Color();

    for (let i = 0; i < n; i++) {
      const { point, colorA, colorB } = colored[i];
      const dim = dimStateFor(point.shortcode, highlightedShortcodes, hoveredShortcode, legendExpanded);
      const isHovered = hoveredShortcode === point.shortcode;
      const scale = (isHovered ? HOVER_SCALE : 1) * dim.scale;

      matrix.makeScale(scale, scale, scale);
      matrix.setPosition(point.position[0], point.position[1], point.position[2]);
      mesh.setMatrixAt(i, matrix);

      tmpColor.set(colorA);
      colorAAttr.setXYZ(i, tmpColor.r, tmpColor.g, tmpColor.b);
      tmpColor.set(colorB);
      colorBAttr.setXYZ(i, tmpColor.r, tmpColor.g, tmpColor.b);
      dimAttr.setX(i, dim.dimmed ? 1 : 0);
    }

    mesh.instanceMatrix.needsUpdate = true;
    colorAAttr.needsUpdate = true;
    colorBAttr.needsUpdate = true;
    dimAttr.needsUpdate = true;
  }, [colored, highlightedShortcodes, hoveredShortcode, legendExpanded, geometry]);

  return (
    <instancedMesh
      ref={meshRef}
      args={[geometry, material, capacity]}
      onPointerOver={(e: ThreeEvent<PointerEvent>) => {
        e.stopPropagation();
        if (e.instanceId === undefined || e.instanceId >= colored.length) return;
        onHover(colored[e.instanceId].point.shortcode);
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={(e: ThreeEvent<PointerEvent>) => {
        e.stopPropagation();
        onHover(null);
        document.body.style.cursor = "auto";
      }}
      onClick={(e: ThreeEvent<MouseEvent>) => {
        e.stopPropagation();
        if (e.instanceId === undefined || e.instanceId >= colored.length) return;
        onSelect(colored[e.instanceId].point.shortcode);
      }}
    />
  );
}

// With the legend collapsed, dimStateFor's usual gray-out-everyone-else
// spotlight is disabled entirely (see its comment) — every point keeps its
// normal look, translucent glow included. This is what provides emphasis
// in that mode instead: a purely additive, non-interactive overlay of
// solid, fully-opaque spheres for whichever shortcodes are currently
// active — the hovered point, or an entire legend-selected theme.
// depthTest is off and renderOrder is high so it always paints on top
// regardless of draw order; the layers underneath are completely
// untouched, this just visually fills them in for the point(s) that need
// to pop.
//
// Sized to MID_RADIUS, not OUTER_RADIUS — OUTER_RADIUS=1.0 needs 2.0
// between two points' centers to avoid touching, and vectorSpace.ts's
// MIN_SEPARATION=2.4 is only a soft *target* from a leash-constrained
// declutter pass, not a hard guarantee for large/dense clusters (see its
// comment) — plenty of pairs in a big theme end up closer than that. Making
// them opaque at OUTER_RADIUS made a selected cluster visibly fuse into
// one blob. MID_RADIUS=0.45 only needs 0.9 apart, safely under even the
// worst-case spacing, so the boosted "main body" of each point stays
// distinct from its neighbors.
function OpaqueBoostLayer({ colored, activeShortcodes }: { colored: ColoredPoint[]; activeShortcodes: Set<string> }) {
  const active = useMemo(
    () => colored.filter((cp) => activeShortcodes.has(cp.point.shortcode)),
    [colored, activeShortcodes]
  );
  if (active.length === 0) return null;
  return (
    <Instances limit={active.length} range={active.length} renderOrder={10}>
      <sphereGeometry args={[MID_RADIUS, 16, 16]} />
      <meshBasicMaterial toneMapped={false} depthTest={false} />
      {active.map(({ point, color }) => (
        <Instance key={point.shortcode} position={point.position} color={color} />
      ))}
    </Instances>
  );
}

const VectorSpaceScene = forwardRef<VectorSpaceSceneHandle, VectorSpaceSceneProps>(function VectorSpaceScene(
  { points, highlightedShortcodes, onSelect, legendExpanded },
  ref
) {
  const palette = useVizPalette();
  // Computed once per palette (not per point/slot) — dualHueSlotsForSlot
  // isn't a hook itself since every call site below needs to invoke it from
  // inside a .map(), where hooks aren't allowed.
  const dualHuePairs = useMemo(() => computeDualHuePairs(palette), [palette]);
  const controlsRef = useRef<OrbitControlsImpl | null>(null);
  const [hoveredShortcode, setHoveredShortcode] = useState<string | null>(null);
  const resetFnRef = useRef<() => void>(() => {});

  useImperativeHandle(ref, () => ({
    resetCamera: () => resetFnRef.current(),
  }));

  const colored = useMemo<ColoredPoint[]>(
    () =>
      points.map((point) => {
        const slot = effectiveSlot(point.colorSlot, legendExpanded);
        // A theme rank that reuses one of the 8 base hues (dualHueSlotsForSlot,
        // slots 8-23) renders its CORE as a true two-tone split further down
        // (see DualCoreLayer) — but the glow layers stay single-color for
        // every point regardless, so their base here is the flat 50/50
        // average of the pair rather than a literal split. Uses the vivid
        // (not the restrained palette) hues so a dual theme's glow still
        // reads as more saturated/eye-catching than a muted single-hue
        // glow, even though the glow itself can't show two distinct colors.
        const dualHues = dualHueSlotsForSlot(slot, dualHuePairs);
        const baseColor = dualHues
          ? mixColor(vividColorForSlot(palette, dualHues[0]), vividColorForSlot(palette, dualHues[1]), 0.5)
          : colorForSlot(palette, slot);
        const blendSlot = point.blendColorSlot && effectiveSlot(point.blendColorSlot, legendExpanded);
        const color =
          blendSlot && point.blendWeight
            ? mixColor(baseColor, colorForSlot(palette, blendSlot), point.blendWeight)
            : baseColor;
        return { point, color, coreColor: lightenColor(color, 0.18), slot };
      }),
    [points, palette, legendExpanded, dualHuePairs]
  );

  // Splits the core layer (not the glow, which stays single-color for every
  // point) into the plain single-hue instances drei's <Instances> renders
  // (soloCoreColored) and the two-tone repeat-hue slots DualCoreLayer's raw
  // shader renders instead (dualCoreColored).
  const { soloCoreColored, dualCoreColored } = useMemo(() => {
    const solo: ColoredPoint[] = [];
    const dual: DualColoredPoint[] = [];
    for (const cp of colored) {
      const dualHues = dualHueSlotsForSlot(cp.slot, dualHuePairs);
      if (dualHues) {
        // Vivid, not lightened-toward-white like the solo cores' "hot" look
        // — lightening here would wash out exactly the saturation/contrast
        // boost vividColorForSlot exists to provide.
        dual.push({
          point: cp.point,
          colorA: vividColorForSlot(palette, dualHues[0]),
          colorB: vividColorForSlot(palette, dualHues[1]),
        });
      } else {
        solo.push(cp);
      }
    }
    return { soloCoreColored: solo, dualCoreColored: dual };
  }, [colored, palette, dualHuePairs]);

  // Only meaningful with the legend collapsed (see dimStateFor/
  // OpaqueBoostLayer) — hover wins over an active legend/search filter,
  // same precedence as the expanded-legend spotlight above.
  const boostShortcodes = useMemo(() => {
    if (legendExpanded) return null;
    if (hoveredShortcode) return new Set([hoveredShortcode]);
    return highlightedShortcodes;
  }, [legendExpanded, hoveredShortcode, highlightedShortcodes]);

  const hoveredPoint = useMemo(
    () => (hoveredShortcode ? points.find((p) => p.shortcode === hoveredShortcode) : null),
    [points, hoveredShortcode]
  );

  // Mirrors hoveredPoint for FocusOrbit's pointerdown handler to read
  // imperatively — a ref instead of a dependency so that handler doesn't
  // need to be torn down and re-registered on every hover change (which
  // fires on nearly every mousemove over the point cloud).
  const hoveredPositionRef = useRef<[number, number, number] | null>(null);
  useEffect(() => {
    hoveredPositionRef.current = hoveredPoint?.position ?? null;
  }, [hoveredPoint]);

  return (
    <Canvas camera={{ position: DEFAULT_CAMERA_POSITION, fov: 50 }} dpr={[1, 1.5]}>
      <color attach="background" args={[SCENE_BACKGROUND]} />
      {/* No lights: every layer below is unlit (meshBasicMaterial) and
          self-illuminated — nothing in the scene reads lighting. */}
      <OrbitControls
        ref={controlsRef}
        enableDamping
        dampingFactor={0.08}
        minDistance={5}
        maxDistance={260}
        panSpeed={1.2}
        screenSpacePanning
        makeDefault
      />
      <ContextLossHandler />
      <CameraController controlsRef={controlsRef} registerReset={(fn) => (resetFnRef.current = fn)} />
      <KeyboardFly controlsRef={controlsRef} />
      <FocusOrbit controlsRef={controlsRef} hoveredPositionRef={hoveredPositionRef} />
      <SpaceBackdrop />
      <BoundingBox />
      <Axes />
      <GlowLayer
        colored={colored}
        radius={OUTER_RADIUS}
        opacity={0.045}
        highlightedShortcodes={highlightedShortcodes}
        hoveredShortcode={hoveredShortcode}
        legendExpanded={legendExpanded}
      />
      <GlowLayer
        colored={colored}
        radius={MID_RADIUS}
        opacity={0.28}
        highlightedShortcodes={highlightedShortcodes}
        hoveredShortcode={hoveredShortcode}
        legendExpanded={legendExpanded}
      />
      <CoreLayer
        colored={soloCoreColored}
        highlightedShortcodes={highlightedShortcodes}
        hoveredShortcode={hoveredShortcode}
        legendExpanded={legendExpanded}
        onHover={setHoveredShortcode}
        onSelect={onSelect}
      />
      <DualCoreLayer
        colored={dualCoreColored}
        maxCount={points.length}
        highlightedShortcodes={highlightedShortcodes}
        hoveredShortcode={hoveredShortcode}
        legendExpanded={legendExpanded}
        onHover={setHoveredShortcode}
        onSelect={onSelect}
      />
      {boostShortcodes && boostShortcodes.size > 0 && (
        <OpaqueBoostLayer colored={colored} activeShortcodes={boostShortcodes} />
      )}
      {hoveredPoint && (
        <Html position={hoveredPoint.position} style={{ pointerEvents: "none" }} zIndexRange={[100, 0]}>
          <div style={{ transform: "translate(24px, -50%)" }}>
            <HoverPreviewCard point={hoveredPoint} />
          </div>
        </Html>
      )}
    </Canvas>
  );
});

export default VectorSpaceScene;
