import { useRef } from "react";
import { motion, useScroll, useTransform } from "framer-motion";
import "./AgentDemoSection.css";

export default function AgentDemoSection() {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"]
  });

  const y = useTransform(scrollYProgress, [0, 1], [100, -100]);
  const opacity = useTransform(scrollYProgress, [0, 0.3, 0.8, 1], [0, 1, 1, 0]);

  return (
    <section className="demo-section-container" ref={ref}>
      <div className="demo-content">
        <motion.div
          className="demo-header"
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
        >
          <h2 className="section-title">
            Agents in <span className="text-neon-pink">Action</span>
          </h2>
          <p className="section-subtitle">Seamlessly integrated into your workflow.</p>
        </motion.div>

        <div className="demo-showcase">
          <motion.div className="video-frame" style={{ y, opacity }}>
            <div className="glass-reflection"></div>
            <div className="video-placeholder">
              <div className="play-button">
                <div className="play-icon"></div>
              </div>
              <div className="placeholder-text">Demo Reel Loading...</div>
              {/* Animated background to simulate activity */}
              <div className="activity-wave"></div>
            </div>
          </motion.div>
        </div>

        <div className="features-grid">
          {[
            {
              title: "Real-time Response",
              desc: "Instant interaction with < 200ms latency."
            },
            {
              title: "Context Aware",
              desc: "Remembers conversation history across sessions."
            },
            {
              title: "Task Autonomy",
              desc: "Executes complex workflows without supervision."
            }
          ].map((feature, index) => (
            <motion.div
              key={index}
              className="feature-card glass-card"
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.2 + index * 0.1, duration: 0.6 }}
            >
              <h3>{feature.title}</h3>
              <p>{feature.desc}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
