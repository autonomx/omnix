import { useEffect, useRef } from 'react';
import {
  resolveCommand,
  tradingCommandDefinition,
  type KeyOverrides,
  type RegisteredCommand,
  type TradingCommandId,
} from './tradingCommands';

const registered: RegisteredCommand[] = [];
let keyOverrides: KeyOverrides = {};
let dispatchers = 0;

export function setTradingCommandKeyOverrides(overrides: KeyOverrides): void {
  keyOverrides = overrides;
}

function dispatch(event: KeyboardEvent): void {
  if (event.defaultPrevented) return;
  const match = resolveCommand(registered, event, keyOverrides);
  if (!match) return;
  event.preventDefault();
  event.stopPropagation();
  match.handler.run(event);
}

/** Installs the one window key listener for trading commands. Mount once, at the trading workspace. */
export function useTradingCommandDispatcher(): void {
  useEffect(() => {
    dispatchers += 1;
    if (dispatchers === 1) window.addEventListener('keydown', dispatch);
    return () => {
      dispatchers -= 1;
      if (dispatchers === 0) window.removeEventListener('keydown', dispatch);
    };
  }, []);
}

/** Binds a component's handler to a catalogued command while the component is mounted. */
export function useTradingCommand(
  id: TradingCommandId,
  run: (event: KeyboardEvent) => void,
  isActive: () => boolean = () => true,
): void {
  const runRef = useRef(run);
  const isActiveRef = useRef(isActive);
  useEffect(() => {
    runRef.current = run;
    isActiveRef.current = isActive;
  });
  useEffect(() => {
    const definition = tradingCommandDefinition(id);
    if (!definition) throw new Error(`Unknown trading command ${id}`);
    const entry: RegisteredCommand = {
      definition,
      handler: { run: (event) => runRef.current(event), isActive: () => isActiveRef.current() },
    };
    registered.push(entry);
    return () => {
      const index = registered.indexOf(entry);
      if (index >= 0) registered.splice(index, 1);
    };
  }, [id]);
}
