// A name for every Terrikin, drawn from a list by its id and the episode it lives in, so the same Terrikin has the
// same name every time that episode plays, and a hatchling gets one of its own. Purely for showing.

const NAMES = [
  'Pip', 'Bix', 'Mo', 'Tuff', 'Nib', 'Wren', 'Pebble', 'Dot', 'Gus', 'Fennel', 'Bramble', 'Sprout', 'Tilly', 'Bodge',
  'Mungo', 'Pumble', 'Quill', 'Rumble', 'Scoot', 'Tansy', 'Umber', 'Waffle', 'Yarrow', 'Zinnia', 'Biscuit', 'Clod',
  'Dumpling', 'Ember', 'Fig', 'Gherkin', 'Hob', 'Inky', 'Jumble', 'Kip', 'Lentil', 'Moss', 'Nutmeg', 'Olive', 'Parsnip',
  'Quince', 'Radish', 'Saffron', 'Truffle', 'Udo', 'Vetch', 'Wobble', 'Yam', 'Ziggy', 'Bean', 'Crumb', 'Dandy', 'Flick',
  'Gumdrop', 'Hazel', 'Ivy', 'Juniper', 'Kettle', 'Loaf', 'Marrow', 'Noodle', 'Oats', 'Pudding', 'Ruckus', 'Sorrel',
  'Thimble', 'Bun', 'Clover', 'Dimple', 'Fudge', 'Gizmo', 'Huckle', 'Jot', 'Kibble', 'Lark', 'Marble', 'Nettle',
  'Oddsock', 'Puddle', 'Rhubarb', 'Snag', 'Tater', 'Wiggle', 'Bloop', 'Chive', 'Dill', 'Fizz', 'Gravel', 'Humble',
  'Jinx', 'Knuckle', 'Lumpy', 'Mallow', 'Nubbin', 'Orbit', 'Pickle', 'Rascal', 'Splodge', 'Tumble', 'Barley', 'Cobble',
  'Doodle', 'Flint', 'Grub', 'Hopper', 'Jojo', 'Kumquat', 'Lolly', 'Mudge', 'Nougat', 'Pod', 'Rusty', 'Smudge',
  'Tadpole', 'Wombat', 'Basil', 'Cinder', 'Drizzle', 'Fumble', 'Gloop', 'Hiccup', 'Jambo', 'Kelp', 'Limpet', 'Muffin',
  'Nimbus', 'Pesto', 'Ripple', 'Sprocket', 'Toffee', 'Widget', 'Bodkin', 'Cress', 'Dusty', 'Fleck', 'Goober', 'Hush',
  'Jasper', 'Kipper', 'Lumen', 'Mops', 'Nacho', 'Plum', 'Rolo', 'Sludge', 'Trundle', 'Whisk', 'Bongo', 'Cumin', 'Dobbin',
  'Frond', 'Gully', 'Honk', 'Jiffy', 'Kale', 'Lugnut', 'Mabel', 'Nugget', 'Pongo', 'Rocket', 'Skipper', 'Tinker',
  'Wally', 'Bramley', 'Caper', 'Dribble', 'Fuzz', 'Gobbet', 'Harvey', 'Jubilee', 'Kudzu', 'Lottie', 'Mortimer', 'Norbert',
  'Percy', 'Roly', 'Sputnik', 'Tofu', 'Wilbur', 'Bubbles', 'Crouton', 'Dodger', 'Fritter', 'Grommet', 'Hamish', 'Jeeves',
  'Klutz', 'Lupin', 'Murphy', 'Nettie', 'Pocket', 'Rummage', 'Spud', 'Tootle', 'Wisp', 'Bumble', 'Cashew', 'Digby',
  'Fiddle', 'Gnocchi', 'Hollis', 'Juno', 'Kernel', 'Ludo', 'Mochi', 'Nell', 'Puck', 'Rosco', 'Squelch', 'Tuck', 'Zest',
];

// FNV-1a, so a name doesn't change between browsers or visits
function hash(text: string) {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

// names for the Terrikins of one episode, keyed by what makes it that episode (its brain and seed): the list is
// walked from a start and in steps both picked by the episode, so no two of its Terrikins share a name until the
// list runs out
export function namesFor(episode: string): (id: number) => string {
  const n = NAMES.length;
  const steps = [7, 11, 13, 17, 19, 23, 29, 31, 37, 41].filter((p) => n % p !== 0);
  const start = hash(episode) % n;
  const step = steps[hash(`${episode}/step`) % steps.length];
  return (id) => NAMES[(start + id * step) % n];
}
