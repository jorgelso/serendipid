"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Grid, Html, Instance, Instances, Line, OrbitControls, Stars, Text } from "@react-three/drei";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import type { VectorSpaceColorSlot, VectorSpacePoint } from "@/types/domain";
import { colorForSlot, useVizPalette } from "@/lib/useVizPalette";
import HoverPreviewCard from "./HoverPreviewCard";

interface VectorSpaceSceneProps {
  points: VectorSpacePoint[];
  activeColorSlot: VectorSpaceColorSlot | null;
  onSelect: (shortcode: string) => void;
}

const POINT_RADIUS = 0.65;
const HOVER_SCALE = 1.6;

// Deliberately independent of the app's light/dark theme tokens — this view
// gets a fixed "lab instrument" aesthetic (see useVizPalette for the one
// place that *does* follow the app theme: the categorical point colors).
const SCENE_BACKGROUND = "#050506";
const DIMMED_COLOR = "#3a3a3d";

// Matches vectorSpace.ts's TARGET_RADIUS (24) with a bit of headroom so the
// axes/grid visibly frame the point cloud instead of clipping it.
const AXIS_HALF_LENGTH = 32;
const AXES: { dir: [number, number, number]; label: string }[] = [
  { dir: [1, 0, 0], label: "X" },
  { dir: [0, 1, 0], label: "Y" },
  { dir: [0, 0, 1], label: "Z" },
];

function Axes() {
  return (
    <>
      {AXES.map(({ dir, label }) => {
        const end: [number, number, number] = [
          dir[0] * AXIS_HALF_LENGTH,
          dir[1] * AXIS_HALF_LENGTH,
          dir[2] * AXIS_HALF_LENGTH,
        ];
        const start: [number, number, number] = [-end[0], -end[1], -end[2]];
        return (
          <group key={label}>
            <Line points={[start, end]} color="white" lineWidth={1} transparent opacity={0.55} />
            <Text position={end} fontSize={1.6} color="#d9d9d9" anchorX="center" anchorY="middle">
              {label}
            </Text>
          </group>
        );
      })}
    </>
  );
}

// A starfield behind everything is what actually fixes "the background feels
// empty" from every camera angle — three large shaded grid planes turned out
// to be too much fragment-shader work at full-screen/retina resolution
// (drove a WebGLRenderer context loss on load). One floor grid plus stars
// keeps the "vector space" cue without the GPU cost.
function SpaceBackdrop() {
  return (
    <>
      <Stars radius={140} depth={60} count={2500} factor={2.4} saturation={0} fade speed={0.4} />
      <Grid
        args={[AXIS_HALF_LENGTH * 2, AXIS_HALF_LENGTH * 2]}
        cellColor="#2c2c30"
        sectionColor="#55555a"
        sectionThickness={1}
        cellThickness={0.5}
        fadeDistance={120}
        fadeStrength={1.5}
        infiniteGrid={false}
      />
    </>
  );
}

// OrbitControls' built-in pan (right-drag / two-finger-drag) is easy to miss
// on a trackpad, and orbiting alone only ever spins around a fixed pivot —
// it can't get you close to a cluster that isn't near the origin. WASD/arrow
// keys translate the camera and the orbit target together, so the user can
// actually fly through the point cloud rather than just rotate around it.
function KeyboardFly({ controlsRef }: { controlsRef: React.RefObject<OrbitControlsImpl | null> }) {
  const { camera } = useThree();
  const pressed = useRef<Set<string>>(new Set());

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
    if (!controls || keys.size === 0) return;

    const { forward, right, move } = scratch.current;
    camera.getWorldDirection(forward);
    right.crossVectors(forward, camera.up).normalize();

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
    controls.target.add(move);
    controls.update();
  });

  return null;
}

function Point({
  point,
  color,
  dimmed,
  onSelect,
}: {
  point: VectorSpacePoint;
  color: string;
  dimmed: boolean;
  onSelect: (shortcode: string) => void;
}) {
  const [isHovered, setIsHovered] = useState(false);

  // Instanced meshes don't support per-instance opacity out of the box (the
  // shared material would need to be uniformly transparent), so "isolate
  // this cluster" is expressed as shrink + desaturate-toward-neutral instead
  // of alpha — visually recedes without fighting the instancing API.
  const effectiveColor = dimmed ? DIMMED_COLOR : color;
  const effectiveScale = (isHovered ? HOVER_SCALE : 1) * (dimmed ? 0.35 : 1);

  return (
    <Instance
      position={point.position}
      color={effectiveColor}
      scale={effectiveScale}
      onPointerOver={(e) => {
        e.stopPropagation();
        setIsHovered(true);
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={(e) => {
        e.stopPropagation();
        setIsHovered(false);
        document.body.style.cursor = "auto";
      }}
      onClick={(e) => {
        e.stopPropagation();
        onSelect(point.shortcode);
      }}
    >
      {isHovered && (
        // No distanceFactor: that scales the card down the farther the
        // camera sits from this point (great for a 3D label, unreadable for
        // a video preview) — the card stays a fixed, legible screen size
        // regardless of zoom instead.
        <Html style={{ pointerEvents: "none" }} zIndexRange={[100, 0]}>
          <div style={{ transform: "translate(24px, -50%)" }}>
            <HoverPreviewCard point={point} />
          </div>
        </Html>
      )}
    </Instance>
  );
}

export default function VectorSpaceScene({ points, activeColorSlot, onSelect }: VectorSpaceSceneProps) {
  const palette = useVizPalette();
  const controlsRef = useRef<OrbitControlsImpl | null>(null);

  const colored = useMemo(
    () => points.map((point) => ({ point, color: colorForSlot(palette, point.colorSlot) })),
    [points, palette]
  );

  return (
    <Canvas camera={{ position: [0, 20, 90], fov: 50 }} dpr={[1, 1.5]}>
      <color attach="background" args={[SCENE_BACKGROUND]} />
      {/* No lights: points use meshBasicMaterial (unlit, always full
          brightness against black) and Line/Text/Grid/Stars are all
          self-illuminated — nothing left in the scene reads lighting. */}
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
      <KeyboardFly controlsRef={controlsRef} />
      <SpaceBackdrop />
      <Axes />
      <Instances limit={points.length || 1} range={points.length}>
        <sphereGeometry args={[POINT_RADIUS, 24, 24]} />
        <meshBasicMaterial toneMapped={false} />
        {colored.map(({ point, color }) => (
          <Point
            key={point.shortcode}
            point={point}
            color={color}
            dimmed={activeColorSlot !== null && point.colorSlot !== activeColorSlot}
            onSelect={onSelect}
          />
        ))}
      </Instances>
    </Canvas>
  );
}
