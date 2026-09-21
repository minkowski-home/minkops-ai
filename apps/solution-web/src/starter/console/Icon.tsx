import type { ComponentType } from "react";
import {
  IconAgents,
  IconAnalytics,
  IconBell,
  IconCheck,
  IconChevronLeft,
  IconChevronRight,
  IconHome,
  IconLogout,
  IconSend,
  IconSettings,
  IconTasks,
  IconX
} from "../components/icons";

export type ConsoleIconName =
  | "agents"
  | "analytics"
  | "bell"
  | "check"
  | "chevronLeft"
  | "chevronRight"
  | "home"
  | "logout"
  | "send"
  | "settings"
  | "tasks"
  | "x";

type IconProps = { className?: string; size?: number };

const icons: Record<ConsoleIconName, ComponentType<IconProps>> = {
  agents: IconAgents,
  analytics: IconAnalytics,
  bell: IconBell,
  check: IconCheck,
  chevronLeft: IconChevronLeft,
  chevronRight: IconChevronRight,
  home: IconHome,
  logout: IconLogout,
  send: IconSend,
  settings: IconSettings,
  tasks: IconTasks,
  x: IconX
};

export function Icon({ name, size = 18 }: { name: ConsoleIconName; size?: number }) {
  const Component = icons[name];
  return <Component size={size} />;
}
