"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { Float, MeshDistortMaterial, Sparkles } from "@react-three/drei";
import { Suspense, useEffect, useRef, useState } from "react";
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

function StaticFallback({ state }: { state: AgentState }) {
  return (
    <div className="flex h-full w-full items-center justify-center">
      <div
        className="h-32 w-32 animate-pulse rounded-full"
        style={{
          background: `radial-gradient(circle, ${STATE_COLORS[state]} 0%, transparent 70%)`,
          boxShadow: `0 0 80px ${STATE_COLORS[state]}`
        }}
      />
    </div>
  );
}

function detectMobile(): boolean {
  if (typeof window === "undefined") return false;
  return /Mobi|Android|iPhone|iPad|iPod/i.test(window.navigator.userAgent);
}

function detectWebGL(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl") || canvas.getContext("experimental-webgl"));
  } catch {
    return false;
  }
}

export function FreddyAvatar({ state = "idle" }: { state?: AgentState }) {
  const [supported, setSupported] = useState(true);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    setSupported(detectWebGL());
    setIsMobile(detectMobile());
  }, []);

  if (!supported) {
    return <StaticFallback state={state} />;
  }

  // На мобильных сильно режем DPR и fillrate, чтобы не лагало
  const dpr: [number, number] = isMobile ? [1, 1.5] : [1, 2];
  const sparklesCount = isMobile ? 30 : 80;

  return (
    <Canvas
      camera={{ position: [0, 0, 4.2], fov: 45 }}
      dpr={dpr}
      frameloop="always"
      gl={{ antialias: !isMobile, powerPreference: "high-performance" }}
      onCreated={({ gl }) => {
        gl.setClearColor(0x000000, 0);
      }}
    >
      <ambientLight intensity={0.4} />
      <pointLight position={[3, 3, 3]} intensity={1.4} color="#a855f7" />
      <pointLight position={[-3, -2, -2]} intensity={1.2} color="#22d3ee" />
      <Suspense fallback={null}>
        <Core state={state} />
        <Sparkles count={sparklesCount} scale={6} size={2.5} speed={0.4} color="#f472b6" />
      </Suspense>
    </Canvas>
  );
}
