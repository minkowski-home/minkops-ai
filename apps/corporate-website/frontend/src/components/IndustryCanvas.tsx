
import { useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { ContactShadows, Environment } from "@react-three/drei";
import * as THREE from "three";

// --- Custom 3D Composed Icons ---

// Fast Food - Burger
function Burger({ color, materialProps }: any) {
    return (
        <group scale={0.6}>
            {/* Bottom Bun */}
            <mesh position={[0, -0.4, 0]}>
                <cylinderGeometry args={[0.9, 0.8, 0.4, 32]} />
                <meshStandardMaterial {...materialProps} color="#E6A65D" /> {/* Bun Color */}
            </mesh>
            {/* Meat */}
            <mesh position={[0, 0, 0]}>
                <cylinderGeometry args={[0.95, 0.95, 0.3, 32]} />
                <meshStandardMaterial {...materialProps} color="#8B4513" /> {/* Meat Color */}
            </mesh>
            {/* Cheese */}
            <mesh position={[0, 0.2, 0]}>
                <boxGeometry args={[1.5, 0.1, 1.5]} />
                <meshStandardMaterial {...materialProps} color="#FFD700" /> {/* Cheese Color */}
            </mesh>
            {/* Top Bun */}
            <mesh position={[0, 0.5, 0]}>
                <sphereGeometry args={[0.9, 32, 32, 0, Math.PI * 2, 0, Math.PI / 2]} />
                <meshStandardMaterial {...materialProps} color="#E6A65D" />
            </mesh>
        </group>
    );
}

// Interior Design - Chair
function Chair({ color, materialProps }: any) {
    return (
        <group scale={0.6} position={[0, -0.4, 0]}>
            {/* Seat */}
            <mesh position={[0, 0.5, 0]}>
                <boxGeometry args={[1.2, 0.2, 1.2]} />
                <meshStandardMaterial {...materialProps} color={color} />
            </mesh>
            {/* Backrest */}
            <mesh position={[0, 1.1, -0.5]}>
                <boxGeometry args={[1.2, 1.2, 0.2]} />
                <meshStandardMaterial {...materialProps} color={color} />
            </mesh>
            {/* Legs */}
            <mesh position={[-0.5, 0, -0.5]}>
                <cylinderGeometry args={[0.1, 0.1, 1]} />
                <meshStandardMaterial {...materialProps} color="#333" />
            </mesh>
            <mesh position={[0.5, 0, -0.5]}>
                <cylinderGeometry args={[0.1, 0.1, 1]} />
                <meshStandardMaterial {...materialProps} color="#333" />
            </mesh>
            <mesh position={[-0.5, 0, 0.5]}>
                <cylinderGeometry args={[0.1, 0.1, 1]} />
                <meshStandardMaterial {...materialProps} color="#333" />
            </mesh>
            <mesh position={[0.5, 0, 0.5]}>
                <cylinderGeometry args={[0.1, 0.1, 1]} />
                <meshStandardMaterial {...materialProps} color="#333" />
            </mesh>
        </group>
    );
}

// Store Owner - Storefront
function Store({ color, materialProps }: any) {
    return (
        <group scale={0.5}>
            {/* Building Base */}
            <mesh position={[0, 0, 0]}>
                <boxGeometry args={[2, 1.5, 1.5]} />
                <meshStandardMaterial {...materialProps} color={color} />
            </mesh>
            {/* Roof */}
            <mesh position={[0, 1, 0]} rotation={[0, Math.PI / 4, 0]}>
                <coneGeometry args={[1.5, 1, 4]} />
                <meshStandardMaterial {...materialProps} color="#333" />
            </mesh>
            {/* Door */}
            <mesh position={[0, -0.25, 0.76]}>
                <planeGeometry args={[0.6, 1]} />
                <meshStandardMaterial {...materialProps} color="#111" />
            </mesh>
            {/* Awning */}
            <mesh position={[0, 0.6, 0.85]} rotation={[0.4, 0, 0]}>
                <boxGeometry args={[2.2, 0.1, 0.6]} />
                <meshStandardMaterial {...materialProps} color="#FF4500" />
            </mesh>
        </group>
    );
}

// Individual - Minimalist Person
function Person({ color, materialProps }: any) {
    return (
        <group scale={0.6}>
            {/* Head */}
            <mesh position={[0, 1.2, 0]}>
                <sphereGeometry args={[0.5, 32, 32]} />
                <meshStandardMaterial {...materialProps} color={color} />
            </mesh>
            {/* Body */}
            <mesh position={[0, 0, 0]}>
                <capsuleGeometry args={[0.45, 1.2, 4, 16]} />
                <meshStandardMaterial {...materialProps} color={color} />
            </mesh>
        </group>
    );
}

// Custom - Abstract Geometric
function Custom({ color, materialProps }: any) {
    return (
        <group scale={0.7}>
            <mesh>
                <icosahedronGeometry args={[1, 0]} />
                <meshStandardMaterial {...materialProps} color={color} wireframe />
            </mesh>
            <mesh scale={0.6}>
                <icosahedronGeometry args={[1, 0]} />
                <meshStandardMaterial {...materialProps} color={color} />
            </mesh>
        </group>
    )
}


// Researcher - Magnifying Glass
function MagnifyingGlass({ color, materialProps }: any) {
    return (
        <group scale={0.7} rotation={[0, 0, Math.PI / 4]}>
            {/* Handle */}
            <mesh position={[0, -1, 0]}>
                <cylinderGeometry args={[0.15, 0.15, 1.2, 32]} />
                <meshStandardMaterial {...materialProps} color="#333" />
            </mesh>
            {/* Rim */}
            <mesh position={[0, 0.8, 0]}>
                <torusGeometry args={[0.6, 0.1, 16, 100]} />
                <meshStandardMaterial {...materialProps} color="#555" metalness={0.8} />
            </mesh>
            {/* Glass Lens */}
            <mesh position={[0, 0.8, 0]}>
                <cylinderGeometry args={[0.6, 0.6, 0.05, 32]} />
                <meshStandardMaterial {...materialProps} color="#E0FFFF" opacity={0.3} transparent />
            </mesh>
        </group>
    )
}


// --- Main Icon Component based on Type ---

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

            // Rotation animation - Slower rotation for floating feel
            groupRef.current.rotation.y += delta * 0.3;
        }
    });

    const materialProps = {
        roughness: 0.3,
        metalness: 0.2,
        transparent: true,
        opacity: opacity,
    };

    const renderShape = () => {
        switch (type) {
            case "person":
                return <Person color={color} materialProps={materialProps} />;
            case "burger":
                return <Burger color={color} materialProps={materialProps} />;
            case "chair":
                return <Chair color={color} materialProps={materialProps} />;
            case "store":
                return <Store color={color} materialProps={materialProps} />;
            case "custom":
                return <Custom color={color} materialProps={materialProps} />;
            case "researcher":
                return <MagnifyingGlass color={color} materialProps={materialProps} />;
            default:
                // Fallback
                return (
                    <mesh>
                        <sphereGeometry args={[0.7, 32, 32]} />
                        <meshStandardMaterial {...materialProps} color={color} />
                    </mesh>
                );
        }
    };

    return (
        <group ref={groupRef} position={targetPosition} onClick={(e) => { e.stopPropagation(); onClick(); }}>
            {renderShape()}
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
        const x = diff * 4.5; // Increased spread for larger models
        const z = Math.abs(diff) * -2.5;

        // Opacity
        const isSelected = diff === 0;
        const opacity = isSelected ? 1 : Math.max(0.2, 1 - Math.abs(diff) * 0.4);

        // Scale - Increased by 3x (from 1.4/0.8 to 4.2/2.4)
        const scale = isSelected ? 4.2 : 2.4;

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
                <ambientLight intensity={0.9} />
                {/* Enhance lighting to show off 3D Details */}
                <spotLight position={[10, 10, 10]} angle={0.3} penumbra={1} intensity={1.5} castShadow />
                <pointLight position={[-5, 0, -5]} intensity={0.8} color="#ffffff" />

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
