import { Pulse, ArrowRight, Barbell, Bicycle, CalendarBlank, CaretDown, CaretRight, ChartLineUp, ChatCircle, Check, Database, GearSix, Heart, House, Mountains, Moon, PersonSimpleRun, User, Wrench, X, ForkKnife } from '@phosphor-icons/react';

export const pageIcons = { dashboard: House, activities: ChartLineUp, health: Heart, training: CalendarBlank, nutrition: ForkKnife, maintenance: Wrench, profile: User, data: Database, settings: GearSix };
export { ArrowRight, CaretDown, CaretRight, ChatCircle, Check, Moon, X };
export function SportIcon({ sport, size = 24 }: { sport: string; size?: number }) {
  const Icon = sport === 'strength' ? Barbell : /cycling|biking|ride/.test(sport) ? Bicycle : /running|run/.test(sport) ? PersonSimpleRun : sport === 'rest' ? Moon : sport === 'hiking' ? Mountains : Pulse;
  return <Icon size={size} weight="regular" aria-hidden="true" />;
}
