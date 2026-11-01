// A gamepad for the kids page, read once a frame: the first one connected, in the browser's standard layout (an Xbox
// controller over Bluetooth on Windows reads as one). Buttons by name, presses counted once, sticks with a dead zone,
// and a buzz where the pad can.

const BUTTONS = { a: 0, b: 1, x: 2, y: 3, lb: 4, rb: 5, lt: 6, rt: 7, view: 8, menu: 9, up: 12, down: 13, left: 14, right: 15 } as const;
export type Button = keyof typeof BUTTONS;
const DEAD = 0.18;

const dead = (v: number) => (Math.abs(v) < DEAD ? 0 : (v - Math.sign(v) * DEAD) / (1 - DEAD));

export class Pad {
  connected = false;
  // left stick (or the d-pad) and right stick, -1 to 1, y down
  move = { x: 0, y: 0 };
  look = { x: 0, y: 0 };
  private now = new Set<number>();
  private was = new Set<number>();
  private pad: Gamepad | null = null;

  poll() {
    this.pad = [...(navigator.getGamepads?.() ?? [])].find((p): p is Gamepad => !!p && p.connected) ?? null;
    this.connected = !!this.pad;
    this.was = this.now;
    this.now = new Set();
    if (!this.pad) {
      this.move = { x: 0, y: 0 };
      this.look = { x: 0, y: 0 };
      return;
    }
    this.pad.buttons.forEach((b, i) => {
      if (b.pressed || b.value > 0.5) this.now.add(i);
    });
    const [lx = 0, ly = 0, rx = 0, ry = 0] = this.pad.axes.map(dead);
    const dx = (this.held('right') ? 1 : 0) - (this.held('left') ? 1 : 0);
    const dy = (this.held('down') ? 1 : 0) - (this.held('up') ? 1 : 0);
    this.move = lx || ly ? { x: lx, y: ly } : { x: dx, y: dy };
    this.look = { x: rx, y: ry };
  }

  held(b: Button): boolean {
    return this.now.has(BUTTONS[b]);
  }

  // down this frame and not the last
  pressed(b: Button): boolean {
    return this.now.has(BUTTONS[b]) && !this.was.has(BUTTONS[b]);
  }

  any(): boolean {
    return [...this.now].some((i) => !this.was.has(i) && i <= BUTTONS.rt);
  }

  buzz(strong: number, weak: number, ms: number) {
    const act = this.pad?.vibrationActuator as { playEffect?: (kind: string, o: object) => Promise<unknown> } | undefined;
    act?.playEffect?.('dual-rumble', { duration: ms, strongMagnitude: strong, weakMagnitude: weak })?.catch(() => {});
  }
}
