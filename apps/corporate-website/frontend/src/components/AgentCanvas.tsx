import { useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { ContactShadows, Environment, Float, OrbitControls } from "@react-three/drei";
import * as THREE from "three";

interface AgentModelProps {
  position: [number, number, number];
  color: string;
  type: "sphere" | "box" | "cone" | "torus";
  isSelected: boolean;
  onClick: () => void;
}

function AgentModel({ position, color, type, isSelected, onClick }: AgentModelProps) {
  const meshRef = useRef<THREE.Mesh>(null!);
  const [hovered, setHover] = useState(false);

  useFrame((state, delta) => {
    if (meshRef.current) {
      if (isSelected) {
         meshRef.current.rotation.y += delta;
      } else {
         meshRef.current.rotation.y += delta * 0.2;
      }
    }
  });

  const scale = isSelected ? 1.5 : hovered ? 1.2 : 1;

  let Geometry;
  switch (type) {
    case "sphere":
      Geometry = <sphereGeometry args={[1, 32, 32]} />;
      break;
    case "box":
      Geometry = <boxGeometry args={[1.5, 1.5, 1.5]} />;
      break;
    case "cone":
      Geometry = <coneGeometry args={[1, 2, 32]} />;
      break;
    case "torus":
      Geometry = <torusGeometry args={[0.8, 0.4, 16, 100]} />;
      break;
    default:
        Geometry = <sphereGeometry args={[1, 32, 32]} />;
  }

  return (
    <Float floatIntensity={isSelected ? 2 : 1} rotationIntensity={1}>
      <mesh
        ref={meshRef} // @ts-ignore
        position={position}
        scale={[scale, scale, scale]}
        onClick={(e) => {
             e.stopPropagation();
             onClick();
        }}
        onPointerOver={() => setHover(true)}
        onPointerOut={() => setHover(false)}
      >
        {Geometry}
        <meshStandardMaterial
          color={isSelected ? "#00ff88" : color} // Highlight color if selected
          roughness={0.2}
          metalness={0.8}
        />
      </mesh>
    </Float>
  );
}

interface AgentCanvasProps {
  selectedId: number;
  onSelect: (id: number) => void;
}

export default function AgentCanvas({ selectedId, onSelect }: AgentCanvasProps) {
  const agents = [
    { id: 0, type: "sphere" as const, color: "#ff0080", position: [-4, 0, 0] },
    { id: 1, type: "box" as const, color: "#4d4dff", position: [-1.5, 0, 0] },
    { id: 2, type: "cone" as const, color: "#ffff00", position: [1.5, 0, 0] },
    { id: 3, type: "torus" as const, color: "#00ffff", position: [4, 0, 0] },
  ];

  return (
    <div className="agent-canvas-container">
      <Canvas shadows camera={{ position: [0, 0, 8], fov: 45 }}>
        <ambientLight intensity={0.5} />
        <spotLight position={[10, 10, 10]} angle={0.15} penumbra={1} intensity={1} castShadow />
        <pointLight position={[-10, -10, -10]} intensity={1} color="#ff0080" />
        
        <group position={[0, -0.5, 0]}>
            {agents.map((agent) => (
            <AgentModel
                key={agent.id}
                type={agent.type}
                color={agent.color}
                // @ts-ignore
                position={agent.position}
                isSelected={selectedId === agent.id}
                onClick={() => onSelect(agent.id)}
            />
            ))}
        </group>

        <ContactShadows position={[0, -2, 0]} opacity={0.5} scale={20} blur={2} far={4} />
        <Environment preset="city" />
        <OrbitControls enableZoom={false} enablePan={false} maxPolarAngle={Math.PI / 2} minPolarAngle={Math.PI / 3} />
      </Canvas>
    </div>
  );
}
