"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { Float, MeshDistortMaterial, Sparkles } from "@react-three/drei";
import { Suspense, useRef } from "react";
import type { Mesh } from "three";

type AgentState = "idle" | "thinking" | "speaking";

const STATE_COLORS: Record<AgentState, string> = {
  idle: "#22d3ee",
  thinking: "#a855f7",
  speaking: "#f472b6"
};

function Core({ state }: { state: AgentState }) {
  const ref = useRef<Mesh>(null);
  const color = STATE_COLORS[state];
  const distort = state === "thinking" ? 0.55 : state === "speaking" ? 0.4 : 0.25;
  const speed = state === "thinking" ? 2.5 : state === "speaking" ? 3.5 : 1.2;

  useFrame((_, delta) => {
    if (!ref.current) return;
    ref.current.rotation.x += delta * 0.15;
    ref.current.rotation.y += delta * 0.25;
  });

  return (
    <Float speed={speed} rotationIntensity={0.6} floatIntensity={1.2}>
      <mesh ref={ref} scale={1.35}>
        <icosahedronGeometry args={[1, 6]} />
        <MeshDistortMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.5}
          roughness={0.15}
          metalness={0.9}
          distort={distort}
          speed={speed}
        />
      </mesh>
    </Float>
  );
}

export function FreddyAvatar({ state = "idle" }: { state?: AgentState }) {
  return (
    <Canvas camera={{ position: [0, 0, 4.2], fov: 45 }} dpr={[1, 2]}>
      <ambientLight intensity={0.4} />
      <pointLight position={[3, 3, 3]} intensity={1.4} color="#a855f7" />
      <pointLight position={[-3, -2, -2]} intensity={1.2} color="#22d3ee" />
      <Suspense fallback={null}>
        <Core state={state} />
        <Sparkles count={80} scale={6} size={2.5} speed={0.4} color="#f472b6" />
      </Suspense>
    </Canvas>
  );
}
