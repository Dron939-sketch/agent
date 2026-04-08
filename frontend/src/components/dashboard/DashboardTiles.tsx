"use client";

import { useState, type ReactNode } from "react";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  rectSortingStrategy,
  useSortable
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Cloud, Calendar, GitBranch, Newspaper, Brain, GripVertical } from "lucide-react";

type Tile = {
  id: string;
  title: string;
  hint: string;
  icon: ReactNode;
  accent: string;
};

// Фабрика плиток. JSX создаётся внутри функции — вызов идёт из
// useState lazy initializer в компоненте, поэтому никакого
// module-init side-effect нет (иначе — риск TDZ в shared chunks).
function buildInitialTiles(): Tile[] {
  return [
    {
      id: "weather",
      title: "Погода",
      hint: "Подключи OpenWeather в .env",
      icon: <Cloud className="h-5 w-5" />,
      accent: "from-neon-cyan/40 to-neon-cyan/5"
    },
    {
      id: "tasks",
      title: "Задачи",
      hint: "Планировщик и напоминания",
      icon: <Calendar className="h-5 w-5" />,
      accent: "from-neon-violet/40 to-neon-violet/5"
    },
    {
      id: "github",
      title: "GitHub",
      hint: "PR, issues, CI статус",
      icon: <GitBranch className="h-5 w-5" />,
      accent: "from-neon-pink/40 to-neon-pink/5"
    },
    {
      id: "news",
      title: "Новости",
      hint: "Дайджест по твоим темам",
      icon: <Newspaper className="h-5 w-5" />,
      accent: "from-neon-lime/40 to-neon-lime/5"
    },
    {
      id: "memory",
      title: "Память",
      hint: "Сохранённые факты и идеи",
      icon: <Brain className="h-5 w-5" />,
      accent: "from-neon-violet/40 to-neon-pink/10"
    }
  ];
}

function TileCard({ tile }: { tile: Tile }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: tile.id });

  return (
    <div
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.6 : 1
      }}
      className="glass group relative overflow-hidden p-4"
    >
      <div
        className={`pointer-events-none absolute inset-0 bg-gradient-to-br ${tile.accent} opacity-60 transition group-hover:opacity-100`}
      />
      <div className="relative flex items-start gap-3">
        <div className="rounded-lg border border-white/10 bg-black/30 p-2 text-white">
          {tile.icon}
        </div>
        <div className="flex-1">
          <div className="text-sm font-semibold">{tile.title}</div>
          <div className="mt-0.5 text-xs text-slate-400">{tile.hint}</div>
        </div>
        <button
          {...attributes}
          {...listeners}
          className="cursor-grab text-slate-500 hover:text-white active:cursor-grabbing"
          aria-label="Перетащить"
        >
          <GripVertical className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

export function DashboardTiles({ id }: { id?: string }) {
  // Lazy initializer — JSX иконок создаётся при первом рендере,
  // а не при импорте модуля.
  const [tiles, setTiles] = useState<Tile[]>(() => buildInitialTiles());
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  function onDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    setTiles((items) => {
      const oldIdx = items.findIndex((i) => i.id === active.id);
      const newIdx = items.findIndex((i) => i.id === over.id);
      return arrayMove(items, oldIdx, newIdx);
    });
  }

  return (
    <section id={id} className="mx-auto max-w-7xl px-6 pb-10">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Дашборд
        </h2>
        <span className="text-xs text-slate-500">перетаскивай плитки</span>
      </div>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={tiles.map((t) => t.id)} strategy={rectSortingStrategy}>
          <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
            {tiles.map((t) => (
              <TileCard key={t.id} tile={t} />
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </section>
  );
}
