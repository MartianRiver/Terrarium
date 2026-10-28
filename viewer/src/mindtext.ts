// Words for the brain window: a short label and a plain explanation for every input, ray kind, action and part.
// Names come from the brain's schema (sim/terrarium/schema.py); one this doesn't know shows as its name.

export interface Words {
  label: string;
  text: string;
}

export const SENSES: Record<string, Words> = {
  energy: { label: 'energy', text: 'How fed it is: 1 just after a good meal, 0 is starving to death. Moving costs energy, faster and turning harder cost more.' },
  forward_speed: { label: 'speed', text: 'How fast it’s going forward, as a share of its top speed (backwards is negative).' },
  side_speed: { label: 'sliding', text: 'How fast it’s sliding sideways, from bumps and turns.' },
  last_thrust: { label: 'last push', text: 'How hard it pushed last time it chose. Its only memory: the brain sees just this moment, plus what it did a moment ago.' },
  last_turn: { label: 'last turn', text: 'How hard it turned last time it chose (left is negative).' },
  home_distance: { label: 'home: far', text: 'How far its nest is, where 1 is as far as it can see (8 m). It always knows the way home, the way an ant counts its steps.' },
  home_sin: { label: 'home: side', text: 'Which side home is on: positive is to its left, negative to its right.' },
  home_cos: { label: 'home: ahead', text: 'Whether home is ahead (1) or behind (−1). With the side, that’s the direction home.' },
  carrying: { label: 'crop', text: 'How full its crop is: food carried in a second stomach to unload into the nest’s store.' },
  at_home: { label: 'at home', text: '1 while it’s inside its own nest.' },
  store: { label: 'store', text: 'How much jelly its colony has stored, for each member: near 1 when there’s plenty, 0 when the store is empty.' },
  light: { label: 'daylight', text: '1 by day, 0 at night, fading in between. Food stops growing at dusk and it gets cold away from the nest at night.' },
  sprinting: { label: 'sprint left', text: 'How much of its current sprint is left.' },
  rested: { label: 'rested', text: '1 when it can sprint again. After a sprint it has to rest before the next one.' },
  holding: { label: 'grip', text: 'How much grip it has left on a block it’s holding. Grabbing is off in this world.' },
  smell: { label: 'smell', text: 'How strongly it can smell food where it’s standing. Scent spreads out from food and fades.' },
  smell_sin: { label: 'smell: side', text: 'Which side the smell gets stronger on.' },
  smell_cos: { label: 'smell: ahead', text: 'Whether the smell gets stronger ahead or behind.' },
  nectar: { label: 'nectar', text: 'How much of a nectar boost it has left: a flower’s nectar makes it faster for 8 s.' },
  load: { label: 'carrying', text: '1 while it carries a berry in its jaws, on top of its head. That berry isn’t eaten: it stays a berry until it’s put down.' },
};

export const KINDS: Record<string, Words & { colour: string }> = {
  nothing: { label: 'nothing', colour: '#9aa3ad', text: 'The ray reached as far as it can see (8 m) without hitting anything.' },
  wall: { label: 'wall', colour: '#6b5a4a', text: 'The garden wall.' },
  creature: { label: 'Terrikin', colour: '#d0569e', text: 'Another Terrikin: a nestmate (ringed) or one from another colony.' },
  food: { label: 'food', colour: '#e0473c', text: 'Food: berries growing, or jelly dropped on the ground.' },
  block: { label: 'block', colour: '#c89b5e', text: 'A wooden block. It can be pushed.' },
  flower: { label: 'flower', colour: '#ffb21f', text: 'An open nectar flower: rare, rich, and gone in 15 s.' },
};

export const ACTIONS: Record<string, Words> = {
  thrust: { label: 'push', text: 'How hard it pushes forward, from −1 (backing up) to 1 (full speed).' },
  turn: { label: 'turn', text: 'How hard it turns: positive is left, negative is right. Turning hard costs energy.' },
  unload: { label: 'unload', text: 'Yes/no: empty its crop. At home that fills the store; away it drops it on the ground as jelly.' },
  eat: { label: 'eat', text: 'Yes/no: eat from its crop, or from the store when it’s home and hungry.' },
  sprint: { label: 'sprint', text: 'Yes/no: a burst at twice its speed for 1.5 s. It costs energy and then it must rest.' },
  grab: { label: 'grab', text: 'Yes/no: grip a block within reach. Off in this world.' },
  carry: { label: 'carry', text: 'Yes/no: pick up a berry within reach, or put down the one it carries. Carrying slows it a little and costs a little energy.' },
};

export const PARTS: Record<string, Words> = {
  senses: { label: 'What it feels', text: 'Its own body and where it is: the numbers that go into its own token. Bars go left for negative, right for positive.' },
  sight: { label: 'What it sees', text: 'Sixteen rays fanned out in front of it. Each ray reports what it hit first and how far away. Brighter rays are the ones it’s paying more attention to right now.' },
  attention: { label: 'Where its attention goes', text: 'Before it acts, its own token asks the ray tokens what they saw. Each head is a separate question asked in parallel, and its weights add up to 1: a bright square is a ray that head is listening to. “me” is the head looking at its own senses instead. The second layer asks again, knowing the first layer’s answers.' },
  summary: { label: 'What it makes of it', text: 'The numbers its own token ends up with after both layers. Every action and its guess at how things are going are read straight off these. One number alone means nothing you could name; it’s the pattern that matters. Warm is positive, cool is negative.' },
  value: { label: 'How things look', text: 'Its guess at how much reward is still to come, used only while training to judge whether a choice turned out better or worse than expected. It doesn’t steer by it, but it shows when the brain thinks things are going well (a meal close by) or badly (starving, night coming, far from home).' },
  actions: { label: 'What it does', text: 'What it chose. For push and turn, the bar is what it wants. For the yes/no actions, the bar is its odds of saying yes, and a tick means it said yes this time.' },
};

export function words(table: Record<string, Words>, name: string): Words {
  return table[name] ?? { label: name, text: 'Something this brain has that this window doesn’t describe.' };
}
