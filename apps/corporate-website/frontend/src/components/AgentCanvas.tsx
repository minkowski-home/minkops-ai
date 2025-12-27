import { useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { ContactShadows, Environment } from "@react-three/drei";
import * as THREE from "three";

// Humanoid shape using primitives
function HumanoidModel({ color, targetPosition, targetScale, opacity, onClick }: {
  color: string,
  targetPosition: [number, number, number],
  targetScale: number,
  opacity: number,
  onClick: () => void
}) {
  const groupRef = useRef<THREE.Group>(null!);

  useFrame((state, delta) => {
    if (groupRef.current) {
      // Smooth lerp to target position
      groupRef.current.position.x = THREE.MathUtils.lerp(groupRef.current.position.x, targetPosition[0], delta * 4);
      groupRef.current.position.y = THREE.MathUtils.lerp(groupRef.current.position.y, targetPosition[1], delta * 4);
      groupRef.current.position.z = THREE.MathUtils.lerp(groupRef.current.position.z, targetPosition[2], delta * 4);

      // Smooth lerp scale
      const currentScale = groupRef.current.scale.x;
      const newScale = THREE.MathUtils.lerp(currentScale, targetScale, delta * 4);
      groupRef.current.scale.set(newScale, newScale, newScale);

      // Breathing animation
      const breathingOffset = Math.sin(state.clock.elapsedTime + targetPosition[0]) * 0.05;
      groupRef.current.position.y += breathingOffset * delta;
    }
  });

  const materialProps = {
    color: color,
    roughness: 0.3,
    metalness: 0.1,
    transparent: true,
    opacity: opacity,
  };

  return (
    <group ref={groupRef} position={targetPosition} onClick={(e) => { e.stopPropagation(); onClick(); }}>
      {/* Head */}
      <mesh position={[0, 1.4, 0]}>
        <sphereGeometry args={[0.4, 32, 32]} />
        <meshStandardMaterial {...materialProps} />
      </mesh>

      {/* Body */}
      <mesh position={[0, 0.6, 0]}>
        <capsuleGeometry args={[0.35, 1, 4, 16]} />
        <meshStandardMaterial {...materialProps} />
      </mesh>
    </group>
  );
}

interface AgentCanvasProps {
  agents: any[];
  selectedIndex: number;
  onSelect: (index: number) => void;
}

export default function AgentCanvas({ agents, selectedIndex, onSelect }: AgentCanvasProps) {

  const getAgentTargetProps = (index: number) => {
    const diff = index - selectedIndex;

    // Position
    const x = diff * 4.5;
    const z = Math.abs(diff) * -2.5;

    // Opacity
    const isSelected = diff === 0;
    const opacity = isSelected ? 1 : Math.max(0.2, 1 - Math.abs(diff) * 0.4);

    // Scale - Increased significantly
    const scale = isSelected ? 4.0 : 2.0;

    return {
      position: [x, -1, z] as [number, number, number],
      scale,
      opacity,
      isSelected
    };
  };

  return (
    <div className="agent-canvas-container">
      <Canvas shadows camera={{ position: [0, 0, 8], fov: 35 }}>
        <ambientLight intensity={0.8} />
        <spotLight position={[10, 10, 10]} angle={0.15} penumbra={1} intensity={1} castShadow />

        <group>
          {agents.map((agent, index) => {
            const props = getAgentTargetProps(index);
            // Render limits
            if (Math.abs(index - selectedIndex) > 3) return null;

            return (
              <HumanoidModel
                key={agent.id}
                color={agent.color}
                targetPosition={props.position}
                targetScale={props.scale}
                opacity={props.opacity}
                onClick={() => onSelect(index)}
              />
            );
          })}
        </group>

        <ContactShadows position={[0, -2, 0]} opacity={0.4} scale={20} blur={2.5} far={4} />
        <Environment preset="city" />
      </Canvas>
    </div>
  );
}
