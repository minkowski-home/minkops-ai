
import { useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { ContactShadows, Environment } from "@react-three/drei";
import * as THREE from "three";

// Geometric shapes for industries
function IndustryModel({ type, color, targetPosition, targetScale, opacity, onClick }: {
    type: string,
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

            // Rotation animation
            groupRef.current.rotation.y += delta * 0.5;
            groupRef.current.rotation.x += delta * 0.2;
        }
    });

    const materialProps = {
        color: color,
        roughness: 0.2,
        metalness: 0.5,
        transparent: true,
        opacity: opacity,
    };

    const renderShape = () => {
        switch (type) {
            case "sphere":
                return <sphereGeometry args={[0.7, 32, 32]} />;
            case "box":
                return <boxGeometry args={[1, 1, 1]} />;
            case "torus":
                return <torusGeometry args={[0.5, 0.2, 16, 100]} />;
            case "cone":
                return <coneGeometry args={[0.6, 1.2, 32]} />;
            case "icosahedron":
                return <icosahedronGeometry args={[0.7, 0]} />;
            default:
                return <sphereGeometry args={[0.7, 32, 32]} />;
        }
    };

    return (
        <group ref={groupRef} position={targetPosition} onClick={(e) => { e.stopPropagation(); onClick(); }}>
            <mesh>
                {renderShape()}
                <meshStandardMaterial {...materialProps} />
            </mesh>
        </group>
    );
}

interface IndustryCanvasProps {
    industries: any[];
    selectedIndex: number;
    onSelect: (index: number) => void;
}

export default function IndustryCanvas({ industries, selectedIndex, onSelect }: IndustryCanvasProps) {

    const getTargetProps = (index: number) => {
        const diff = index - selectedIndex;

        // Position
        const x = diff * 2.5;
        const z = Math.abs(diff) * -2;

        // Opacity
        const isSelected = diff === 0;
        const opacity = isSelected ? 1 : Math.max(0.2, 1 - Math.abs(diff) * 0.4);

        // Scale
        const scale = isSelected ? 1.4 : 0.8;

        return {
            position: [x, 0, z] as [number, number, number],
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
                <pointLight position={[-10, -10, -10]} intensity={0.5} color="blue" />

                <group>
                    {industries.map((industry, index) => {
                        const props = getTargetProps(index);
                        // Render limits
                        if (Math.abs(index - selectedIndex) > 3) return null;

                        return (
                            <IndustryModel
                                key={industry.id}
                                type={industry.shape}
                                color={industry.color}
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
