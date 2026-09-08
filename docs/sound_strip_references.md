# The score strip: what it is, what it borrowed, and what it refused

The recording strip at the foot of the workbench stage (`web/components/ScoreStrip.tsx`,
`web/lib/hearing.ts`) went through two designs in September 2026. This note records
both, so the second is not undone by someone rediscovering the first.

## The idea it serves

The building is frozen music. The compiler heard the recording once, took its
measurements, and drew everything from those numbers. The strip therefore shows the
recording **as the score it was read as** — whole, still, left to right — and never as
a player. Two things follow, both from the user's direction:

- **Nothing moves with playback except a hairline.** A moving timeline, a bouncing
  spectrum, a beat pulse all say "the music is happening now", and a viewer infers
  that the building answers to it. It does not. Listening is available, small, and
  changes nothing else on the page.
- **No spectrum as the face of the music.** Spectrum in, form out is the cliché of
  this genre, and the first impression the project must not give. A spectrum appears
  in exactly one role: as *raw material* that the reading is drawn out of.

## The score

Every mark is a measurement the compiler reported (`audio_features`), in a vocabulary
a musician already reads:

| Measurement | On the staff |
|---|---|
| the six segments | six measures, bar lines at the compiler's cuts, a double bar at the end |
| onset density per segment, against the track's busiest | how many notes the measure holds: one quarter note when sparse, a beamed run of eighths when busy (1–8) |
| spectral centroid per segment, log-scaled across the track's range | where the notes sit on the staff — brighter sits higher |
| RMS loudness per segment, against the track's mean | the dynamic under the measure: *p* · *mp* · *mf* · *f* |
| tempo | the metronome mark at the head, ♩ = bpm |

Hovering a measure names what it was drawn from: "Measure 3 · f · busier · brighter ·
0:14–0:21". The full measurements, with method and confidence, are in the Audio report.

## The engraving

The sheet is set in **Bravura**, Steinberg's reference font for SMuFL (the Standard
Music Font Layout), under the SIL Open Font License; the font and its licence sit
unmodified in `web/public/fonts/` (the OFL reserves the name, so it is shipped whole
rather than subset). SMuFL's one rule does the sizing: one em is four staff spaces, so
every glyph set at 4 × the staff gap is engraved to scale. The clef, noteheads,
dynamics and metronome mark are glyphs; the staff, bar lines, stems, beams and
hairpins are strokes at Bravura's own engraving thicknesses (`web/lib/smufl.ts` keeps
the handful of metrics — notehead width and stem anchor, clef box, dynamic ink extents,
line thicknesses — from `redist/Bravura.json`). If the font has not arrived within three
seconds the sheet falls back to drawn heads and a serif dynamic rather than glyph boxes.

## The motion

Four movements, all the score's own, all through anime.js on the SVG, each borrowed
from a place where scores already move:

1. **A reading is written.** The machine's hearing — the whole piece's log-frequency
   picture, computed once, offline, at 16 kHz (`decodeHearing`) — surfaces for a
   moment; the staff draws across it; the clef and the metronome mark pool in; then
   measure by measure the bar line is ruled, the heads rise out of the field, the stems
   are drawn, the beam is ruled from the left, the dynamic and its hairpin follow —
   while the hearing dissolves. Stroke by stroke, the way
   [Legumes](https://github.com/LingDong-/legumes) renders a score as polylines to be
   drawn in order. The spectrum is there to be read, and is gone in two seconds.
2. **Listening follows the score.** A hairline moves along the staff and the measure
   it is in takes the accent — the score-follower of
   [abcjs](https://github.com/paulrosen/abcjs) (`TimingCallbacks`, highlighted notes),
   [OpenSheetMusicDisplay](https://github.com/opensheetmusicdisplay/opensheetmusicdisplay)
   (its cursor) and [alphaTab](https://github.com/CoderLine/alphaTab) (beat and bar
   cursor). Nothing outside the sheet responds.
3. **A measure under the pointer** lifts, takes the accent, and its patch of the
   hearing returns beneath its notes: where they came from.
4. **A compile** puts the score on the stage with a reading line sweeping the empty
   staff, and the clock. Nothing plays.

The hairpins themselves are engraving practice rather than motion — the wedge every
score prints where a passage grows or fades ([VexFlow](https://github.com/0xfe/vexflow)
draws them as `StaveHairpin`) — and here they mark a measure whose neighbour is louder
or softer, which is the *tension / release* the score dimension is named for.

`prefers-reduced-motion` collapses all four to the finished score.

## The fifth movement: the score becomes the building

The user's next ruling: a score that freezes *as a score* stops half-way. "Frozen
music" has to freeze into the building, and the relationship between the score and
the modelling has to be visible. The reference the user named is the abstraction of
painting — the object drawn down to geometry, Mondrian's tree becoming lines becoming
a grid (*Grey Tree* 1911 → *Flowering Apple Tree* 1912 → *Composition* 1913) — with
the instruction to make our own version of it. Ours has four rungs, and every rung is
a thing the pipeline actually produces, in the order it produces them:

| Rung | On the stage | Where it comes from |
|---|---|---|
| the field | the machine's hearing, a log-frequency picture of the whole piece | `lib/hearing.ts`, offline |
| the marks | the score written out of that field | `analysis.segments` + features, engraved in Bravura |
| the lattice | level lines and bay lines drawn in the model's own space, a three-dimensional registration grid | `analysis.lattice` — levels, `x_lines`, `y_lines`, plan |
| the building | the elements rising *onto* those lines, layer by layer | the GLB, assembled in construction order |

The lattice is the rung that was missing. It is the exact counterpart of the painter's
grid: the moment the measured thing (tempo of change → level count, tension / release
→ floor-to-floor, density → bay) has become pure geometry, before anything is built on
it. `LatticeLines` in `ArchitectureViewport.tsx` draws it as strokes — the level
rectangles bottom to top, then the bay verticals at the crossings — over 2.6 s, while
the feed's stage 00 speaks and the model is *held* below ground (`hold`): nothing
stands until there are lines to stand on. When the assembly finishes, the lattice
fades; the building is what remains of it.

The order is enforced, not hoped for. The stage *arms* a performance (first open,
Play, a landed compile) and only *starts* it when the strip reports that the reading
has been written (`onEntered`), with a five-second fallback for a recording that
cannot be decoded; Play rewrites the score from its hearing before the building
returns, so a replay is the whole ladder every time.

### The crossing, and the reading it must not give

The first crossing lit the *marks* a layer's dimensions had been read from — note heads
for density, dynamics for tension / release — and ran a leader from those marks to the
largest element of the layer as it rose. The user's ruling on seeing it: that reads as
"the building is built note by note", and it is not. The compiler reads the **whole**
recording; a score dimension is one number for the whole piece; a datum is one rule
that then holds everywhere in its layer. The chain spectrum → score → building is
sound; the *visual* had to say whole → number → rule. The user pointed at computer
vision and at TouchDesigner, "where audio visualisation is done best", for what to
borrow. What was borrowed, and from where:

- **The analysis bracket** (music theory). A reading of a passage is written *under*
  the staff, spanning every bar it is about — phrase brackets, form labels, the Roman
  numerals of harmonic analysis. So the sheet now draws one bracket under **all six
  measures**, labelled *all 6 measures → Density 0.26*. Nothing on a note lights.
- **The accumulator vote** (computer vision: the Hough / Radon transform —
  [Hough transform](https://en.wikipedia.org/wiki/Hough_transform); Radon and Hough as
  one thing, [a unifying perspective](https://www.researchgate.net/publication/303683410_The_Radon_transform_and_the_Hough_transform_a_unifying_perspective)).
  Every point of an image votes; the reading is a *peak* in a small parameter space;
  the line drawn back from the peak holds across the whole image. That is exactly
  what a score dimension is, and the motion says it: a reading window sweeps the
  entire staff and seventy-two votes, from every measure alike, stream into the
  bracket's label. The number is the peak.
- **The number moves the field, not the mark** (TouchDesigner). In TouchDesigner's
  audio-reactive idiom the spectrum is *material* — Audio Spectrum CHOP → CHOP to TOP —
  and what moves the picture is an analysed value driving a whole instanced field at
  once, every instance answering to the same number
  ([audio-reactive instancing](https://alltd.org/audio-reactive-instancing-touchdesigner-tutorial-008/),
  [reactive CHOP](https://derivative.ca/community-post/tutorial/reactive-chop-touchdesigner-tutorial-08/70452),
  [the beginner's guide](https://interactiveimmersive.io/blog/touchdesigner-lessons/audio-reactive-visuals-a-beginner-guide/));
  a Trace SOP turns a whole field into contours. The leader from the sheet therefore
  starts at the **number** on the bracket and lands on a **rule** in the model.
- **The dimension string** (drawing practice). A drawing states a rule that holds
  everywhere as a string with a tick at every line it governs: *6 × 4.2 m*. So the
  datum in transfer is drawn in the model's space as a dimension string across the
  whole lattice — the level string at the plan corner with a tick at every level for
  floor-to-floor, the bay string along the ground with a tick at every bay line for
  the bay — and a datum with no lattice geometry is stated once, over the whole
  layer (*plate cantilever 2.2 m · whole layer*), never on one element.

The links are still not authored: `lib/links.ts` reads them off the run — the
translation report says which datums each dimension set and which element kinds those
datums reach, the element groups say which layer each kind is in, and the mapping
rules say which parameter family a dimension targets (`lattice.`, `grid.`,
`sequence.` → the lattice). A layer's links are spoken one at a time, 1.7 s each; the
footer names each in plain words: *Structure ← Density 0.26 → bay, long axis 7.2 m ·
bay, short axis 7.8 m · joist spacing 2.3 m · 2/6*. Hovering a keynote holds its
layer's links up the same way. The recording that shows it end to end is
`artifacts/evidence/workbench_walkthrough/score_to_building.mp4`.

TouchDesigner itself is now reachable as compute support — `tools/td_mcp/` is a Web
Server DAT that speaks MCP — for trying the next motion idea at full quality before it
is ported to the sheet.

## The sixth movement: the hearing as a cloud, and the survey on it

The user's next asks, in order: the audio as *dynamic particles*, "like casting a
spell — every time a new piece of the building appears, the particles sweep over and
become the solid"; then "box parts of the particles to show the rhythm analysis of a
passage — one datum, one box — and join the boxes with a data net"; then a set of
references and the ladder in five words: **音乐 → 图形 → 抽象 → 几何 → 建筑** (music →
graphic → abstraction → geometry → building).

The references, described rather than reproduced: a photogrammetry point cloud of a
tree with survey frames pinned to it, each frame captioned in small monospace (id,
name, time, date, coordinates) and joined to the others by long straight white lines;
a tulip measured with numbered boxes and a web of lines; a white rose collaged with
circuit boards, grids and columns of numbers; a hand-drawn field of dots, nodes and
radiating lines; a blue-on-paper poster of dot clouds, grids and charts; a ruled sheet
with birds, calligraphy and long horizontals. What they share: the *object as a field
of points*, and an *annotation layer* of thin frames, tiny captions and lines that
cross the whole picture — the survey, not the object, is what is drawn.

What was built (`web/components/HearingCloud.tsx`):

- **The graphic.** The machine's hearing — the very field the score was written out
  of — hangs in the model's space as a ribbon of some fourteen thousand particles in
  the open air beside the plan: time along the ribbon, frequency as height, every
  particle seeded from a cell of the field, louder cells more often. It is born the
  moment the score has been written (the same instant the lattice starts), so the
  hearing that dissolved on the sheet reappears in three dimensions.
- **The abstraction.** One wire frame per part of the recording boxes that part's
  particles, with a survey caption at its near corner in monospace — `part 3
  0:14–0:21 / onsets 2.0/s · rms 0.144 · 1293 Hz`, the compiler's own per-part
  measurements — and a net of lines runs from every box to the whole-piece numbers
  those readings were folded into (*Density 0.26* from the onsets, *Tension /
  release 0.21* from the loudness), with a chain along the parts for the order they
  were read in. Captions stagger over three rows the way a survey staggers labels
  that would touch. The net draws itself stroke by stroke in the first 1.4 s.
- **The geometry.** The lattice now waits 1.6 s for the net, then draws: graphic,
  abstraction, geometry, in that order, all under stage 00.
- **The building.** Each particle belongs to one element of the building, drawn by
  surface area across the whole layer (the site excluded), and its cell of the
  hearing is drawn at random from the whole piece — so when a layer's turn comes the
  particles that belong to it leave the ribbon from everywhere, spiral across, and
  land on the element's surfaces exactly as it arrives, then go out because the
  element is solid now. The ribbon thins as the building stands; when the building
  is complete the recording has been spent. Nothing local: no note builds a column,
  and the earlier ruling holds.

The whole cloud is one GPU point buffer whose every position is a pure function of
the assembly's clock (`AssemblyClock`: elapsed, step, rise, live, done — published by
the assembly loop, read by the shader through three uniforms), so Skip, Play and
reduced motion fall out for free and no CPU work happens per frame. The idiom is
TouchDesigner's — a field of instanced points moved by analysed values — and the
survey layer is the references'. Mode-aware: additive pale points and pale wires on
the blueprint, dark points and ink wires in the studio.

## The hearing lab: the analysis on its own

The user then asked to set the building aside and see the *front* of the ladder by
itself — the recording analysed and taken apart, in the register of the references.
`web/app/hearing/page.tsx` → `HearingLab.tsx` is that: the demo track's hearing as a
field of points (time × log-frequency, loudness as relief), a reading window sweeping
it in; a frequency rule and a clock; loudness and centroid per column as curves read
off the field on the spot; a wire box per part with its three measurements as a
monospace survey caption and a small bar chart; the twelve whole-piece measurements
as diamond nodes above, netted from the parts that feed them; the ten score
dimensions as nodes below, netted from the measurements named in each one's
`source_feature`. Everything is drawn stroke by stroke on a cue sheet (`CUE`), the
captions fade in on theirs, and the camera orbits slowly afterwards. Everything on
screen is the run's own numbers; nothing is authored. Recording:
`artifacts/evidence/workbench_walkthrough/hearing_lab.mp4`.

## The live view: the lab with its constraints off

The user's next instruction, for the lab only: drop the constraints and turn the
spectrum into a 3D particle effect, then put the analysis frames on it. Their
references this time: a thunder-simulation render on a drawing sheet (a wispy cloud of
particles over a fine grid, metre scales on the edges, a title block with a
waveform); a "logic of machinism" poster (particle wisps at numbered stages, a ruler,
trajectories with crosses and coordinate captions like `b1[27,20,18,15]`, dashed
guides); a poster where a glossy cloud dissolves into a dotted mesh. So
`LiveSpectrum.tsx` (the Live view of `/hearing`) is the one place in the workbench
where playback *does* move the picture — there is no building there to mislead about.
An analyser writes one 256-bin log spectrum per frame into a 256 × 512 texture; the
GPU draws every row as a line of points lifted by loudness, receding with age and
drifting into wisps under a slow turbulence (loud cells most); fifty thousand sparks
on looping lives read the loudness of their band at their birth row and are thrown
only by loud cells. Over it, rebuilt on the CPU each frame from the per-row readings:
the smoothed centroid as a warm thread; a cross above the crest at every onset a
spectral-flux detector fires, captioned `e12 [t, band, level]`; a wire frame per
six-second stage with its mean loudness and centroid; the warm frame of the last
1.5 s with the live numbers; a ruler of seconds along the edge; the frequency scale in
front. Recording: `artifacts/evidence/workbench_walkthrough/live_spectrum.mp4`.
The rule for the *stage* is unchanged: nothing there moves with playback.

## The mass: nebula, school, and the ring's breathing

Then: "先去掉边框约束，专注于呈现出有艺术效果的3d粒子特效团，像星云像鱼群", and "要有
呼吸感 — FFT 环本身就挺有呼吸感的要继承这个优点". So the Live view of `/hearing` became
`NebulaSpectrum.tsx` and the framed version moved to a *Frames* button. It is a GPU
particle simulation — 512 × 512 positions and velocities in ping-pong float render
targets, three shader passes a frame (velocity, position, points), the idiom of
TouchDesigner's particlesGPU with a noise force. Every particle belongs to one band;
the bands run around a ring, bass to treble, so the FFT ring's virtue is kept: each
band's live loudness pushes its sector outward and lifts it, and the sector's cloud
fattens with it. On top of that, the breath: the whole radius swells with the
passage's energy smoothed over about a second, pulses with the bass, and an onset
(spectral flux above its running mean) throws the entire mass outward for a moment.
A curl-noise flow (the curl of a folded-sine potential, divergence-free, slowly
turning) and one slow stream around the ring carry every particle together, which is
what makes it read as a school rather than a swarm; springs to each particle's home
and damping bring it back, so the mass overshoots and settles like a body breathing.
Drawn twice, additively — faint small points and a sparse pass of large soft ones for
the nebula's cores — with the workbench's pale blue running to its warm accent with
loudness. A quarter of a million points need very faint ink: the first take was a
white blob until the per-point alpha came down to a few hundredths. Recording:
`artifacts/evidence/workbench_walkthrough/nebula_spectrum.mp4`. This view, like the
rest of the lab, is exempt from the stage's playback rule; the stage is not.

### Then: solid, and pulling on itself

"我想要实心的会自我拉扯的粒子团，FFT 环只是举个例子." So the ring went. The body is
now a volume: every particle keeps a radial slot of its own inside a ball (a spring
along its own direction, not to a point), which keeps the mass solid and full while
letting it deform. Inside it live eight cores, one per band group, bass to treble,
each on a slow orbit of its own; a core's reach grows with its group's loudness, so
a loud group's core moves out towards the surface and beyond, and its particles are
pulled into a knot that stretches out of the body as a limb — the cores pulling
against one another and against the slots is the tug. A core keeps a small hollow
around itself and its grip is capped, so the knots are flesh, not needles. The
passage's energy swells the slots, the bass pulses them, an onset throws the whole
body outward, and a curl flow keeps the inside moving. Recording as above.

"速率再快一点，3秒内要让人看出明显变化": the ear's smoothing came down (analyser
0.5, core energy over ~3 frames, breath over ~8), the cores orbit three times faster
and reach further, the body's spring and damping both went up so it snaps and settles
inside a second, the flow and the onset burst are stronger, and the camera turns
faster. Any three seconds of the track now read as a different body.

"变化再复杂一点": fourteen cores now, of three kinds by turn — pullers, spinners
(their pull carries a swirl, so the limb they throw is a vortex) and pulsers (their
grip beats at six a second); two octaves of turbulence, the fine one stirred by the
treble; a torsion that turns the upper and lower halves against each other and slowly
reverses; a bass-driven split into two lobes along a wandering axis; a shock ring
that travels out through the body from the centre at every onset (the last three
kept); and a treble fizz on the surface. All in the one velocity pass.

"增强丝带/极光感": the picture is now a feedback — each frame is drawn onto the last
one faded towards the ground colour (TouchDesigner's Feedback TOP), so every particle
leaves a ribbon, longer in loud passages (the fade follows the breath); a five-tap
softening and a soft shoulder on presentation let the bright ribbons bloom instead of
clipping. The palette moved to an aurora's: green at the bass, cyan through the mids,
violet at the treble, warm white where the spectrum is hot; and the flow pulls
vertically, so the ribbons hang like curtains. The render loop is taken over
(`useFrame(…, 1)`): fade pass, scene pass, present pass.

"我想要更明显的弯曲感，被风吹起来的那种飘动感", with the thunder-simulation sheet
sent again: a *wind* — a slowly turning direction that gusts on the bass and the
onsets — and a wave that travels through the body along it, so the sheets bend in
S-curves and flutter, more at the top the way a curtain moves most at its free edge;
the body leans a little downwind and its slots are held loosely, so it sways back.
Toward the reference: the body is a tall thin veil, the ink a third of what it was,
lilac at the bass and pale blue through the mids on a near-black ground, the drift
slower and floatier (less damping, slower waves, slower cores), the trails longer.

"现在开始叠加分析框": the survey comes back, on the mass this time, in the thunder
sheet's register. It is drawn in a scene of its own after the feedback picture is
presented, so its lines stay crisp while the particles trail. A wire box around every
core that is loud — one datum each: `c4 [144 Hz-222 Hz] / level 0.81 at -6.2, -11.7,
9.4`, its band, its level, its place — and a faint net from each box to the readouts
above (loud, centroid, flux, bass, live); a warm cross fixed where each onset struck,
captioned `e12 [t, band, level]`, fading over six seconds; metre scales on the right
and bottom edges; a fine grid behind. Captions are the same pooled monospace divs
as the Frames view.

"先只画方框，不要坐标轴不要立方体不要标签": the survey stripped back to its first
element — flat rectangles only, one around each loud knot, sized by its level and
facing the camera (DOM rectangles placed by projecting the knot and two offsets along
the camera's right and up), nothing else drawn. The scales, grid, readouts, net and
crosses stay in the code behind the Survey toggle's next steps.

"方框网络", with a poster of squares joined by straight lines (some heavy, some
dashed) as the reference: the frames are now a network. Edges, drawn as an SVG in the
overlay so they stay crisp: a chain through the bands in order, a hub from the
loudest box to every other, and each box's nearest neighbour on screen; an edge's
weight is the loudness it joins — heavy above 0.45, heavy and dashed above 0.7.
Still no labels, no axes, no cubes.

"音频粒子云要放大到屏幕的75%，然后方框要缩小一点，且方框要框中粒子云的某个部分，并
标示出我们翻译出来的维度数据": the camera came in so the cloud fills about three
quarters of the frame, and the boxes are now read off the simulation — a 40 × 40
read-back of the position texture each frame (1,600 particles, their band in the
alpha channel), projected, grouped into ten band groups, each box the 30th–70th
percentile of the half of its group nearest the knot its core has gathered, smoothed —
so every box frames a real, distinct part of the cloud rather than its middle. Ten boxes, one per translated score dimension in the run's order, each
carrying that dimension's name and value (*Density 0.26*, *Tension / release
0.21*…); the network's edge weights come from the group's live share of the spectrum.

"有点不够显眼 … 前期过小 + 后期超出边界 … 看不清 … 粒子云太实了，我想要更粒子一点的": the
camera now frames the cloud itself — from the read-back, its centre is the orbit
target and its 92nd-percentile radius sets the distance, both eased — so the cloud
holds about three quarters of the frame whether the passage is quiet or loud. The
survey is bolder: 1.5 px white frames with a dark halo, labels on a dark backing,
heavier edges. And the cloud reads as particles again: the feedback trail is short
(a quarter of a frame's persistence), the points small and faint, and only 42 % of
the quarter million are drawn, so dots stay dots instead of fusing into ribbons.

"为什么粒子是单独成条状的，看起来是彼此独立的，而不是一个会呼吸的整体": the strands
were the trails — every particle's path drawn as a line, and neighbours under the same
forces running in parallel, so the body read as a comb of independent lines. Three
changes: the feedback trail is gone (a few percent of persistence), a fine
per-particle turbulence makes neighbours weave, and 72 % of the particles are drawn,
small and faint, with the glow pass binding them. And the dynamics moved toward one
body: the whole volume's swell with the breath and its pulse with the bass are now
the largest forces; the cores' grip is capped low and their reach kept inside the
body, so they dent its surface instead of tearing limbs off; the split and the shared
flow are gentler; the slot spring firmer, the hold softer.

"方框的面积相对于粒子云来说太大了 … 方框框选的部分我想给一个反色": the boxes are
tighter (the nearest 30 % of the group's particles, 15th–85th percentile), capped at a
fifth of the cloud's own extent on screen, and a box whose centre falls inside one
already placed is skipped, so they never pile. What a box frames is inverted: the box
is a white rectangle in `mix-blend-mode: difference` over the canvas, so the ground
goes light and the particles dark inside it — a negative, cut out of the picture. The
labels moved out of the boxes into their own tags, so they are not inverted with it.

"然后现在做从粒子云里不停飞出的一撮撮粒子构成了一层层建筑构建": `Builders.tsx`. The
run's GLB is sampled by surface area, layer by layer in construction order (site,
structure, envelope, circulation, program; sixty thousand points, no slab allowed
more than 4 % of its layer), fitted beside the cloud at a fixed height. Every point
waits in the cloud until its clump's turn — each layer has five seconds, a clump
leaves every 0.28 s from one spot of the cloud — then arcs across with a bright head
and settles on its element, coloured by layer. The building stands for six seconds,
fades, and the cycle restarts (31 s), so the cloud never stops giving. The camera
holds the pair: the orbit target sits between the cloud's centre and the building,
and the distance covers both. All of it is a pure function of the clock.

"意思到位了，但是要做得再 delicate，现在太像火山喷发了，我想要的效果是魔法棒施展魔法":
the bursts became a wand's thread. Births are spread evenly through each layer's
window, element after element, so the wand traces the building; the thread leaves the
cloud from a tip that glides over its surface (a slow Lissajous), so particles born
together form one thin line instead of a clump; the path is a quadratic arc with a
helix around it that tightens as it lands; the dust in flight is gold-white and
twinkles, and each particle flashes white on arrival before settling into its
layer's colour, small. The flight is longer (3.4 s), the points finer, and the site
is a sprinkle (a third of a layer's share) rather than a dotted plain.

"要调整运镜让重点从音乐（粒子）→建筑（生成动画）之间有个平滑过渡" and "粒子团可以围绕
建筑进行盘旋": the camera now has one arc through the cycle — it opens on the cloud
while the first thread leaves, glides to the building as the layers stand (the orbit
target and the distance both eased along a smoothstep of the cycle clock), stays with
the finished building, and returns to the cloud as it fades. The survey's boxes, tags
and net fade out as the camera leaves the cloud, so each moment has one subject. And
the cloud itself circles the building while it casts (a slow orbit, radius 27, with a
gentle vertical bob); the threads leave from wherever it is, since each particle's
launch anchor is the orbit evaluated at its own birth time. Point sizes are capped in
every shader so near-camera dust never balloons into bokeh.

"粒子云怎么飞出的粒子簇和脱节了，而且由于运动的关系粒子云看不出来是音乐效果了，还是做成
前后景的退隐交换吧": the orbit went. Moving the cloud broke both readings — the threads
looked severed from it (their launch anchor was the orbit at each particle's own birth
time, so the emission point lagged the cloud) and a travelling cloud stopped reading
as the music. Now the two are on one axis, foreground and background: the cloud hangs
still at z = +11, breathing with the spectrum, and the building stands behind it at
z = −15. The exchange is a recession, not a camera move — the cloud's points dim to a
fifth as the focus rises, the settled building brightens from a third to full, the
survey fades with the cloud, and the camera only tilts and pushes gently between the
two planes. Every thread now leaves the cloud's own centre, so nothing is severed.

"改成前3-5s专注于粒子云的出现，然后分析框出现，不使用反色了有点乱，10s开始粒子云退隐
到背景里+建筑生长动画": the cycle is now acted, and its clock starts when the listener
presses play rather than when the page loaded. 0–3.2 s the cloud gathers alone; 3.5–5 s
the frames and the net fade in over it; 5–10 s both hold; from 10 s the focus rises,
the cloud recedes to a fifth of its brightness with the survey fading with it, and the
building grows behind — four seconds a layer, twenty in all; it holds five seconds,
fades, and the cloud returns for the last second so the loop has no seam. Thirty-five
seconds in all. The inversion is gone: the frames are plain white outlines on a faint
tint. One trap worth recording: the timeline was briefly computed *inside* the block
that the survey gate opened, so the gate closed on its own inputs and the whole
sequence froze at zero — the read-back, the timeline and the camera must always run,
and only the drawing may be gated.

"粒子云团的面积在音乐的不同阶段差距太大 … 高潮应该增加的是粒子团内部波形的分化数量和
抖动程度，并非面积上无限平铺 … 从开始就放大到允许溢出边界": the envelope is now held.
Each particle's radial slot is fixed (0.94 of the body, with a twelfth of a breath of
swell and a twentieth from the bass), a cage pulls back anything pushed past 1.22 of
it, and the bass lobe split is halved — so quiet and loud passages occupy the same
area. The climax goes inside instead: the cores grip three times harder while their
reach is kept well within the body, so a loud passage grows more lobes rather than a
wider cloud; the fine turbulence scales with the band's energy and the breath; and
every particle trembles with its own band at twenty-two shakes a second. The camera
sits close from the first frame (distance ≈ 2.4 radii, floor 17) so the cloud fills
and overflows the frame rather than reading as a speck.

"这个喷洒的粒子簇和粒子云看起来根本没关系，我需要的是从粒子云中心发射": the wand's
gliding tip is gone. Every thread now leaves the cloud's own heart — a source less
than a unit across at the centre — and that centre is not a constant but the
simulation's measured centre of mass, handed to the builders' shader each frame and
eased, so the source sits inside the cloud however it breathes or leans. The stream
reads as drawn out of the mass rather than sprayed from the air beside it.

"粒子云不能因为建筑的出现而缩小，要保持固定大小，但是逐渐隐退到建筑后方并降低存在感":
the withdrawal is now a true recession. The cloud's anchor travels from z = +11 to
z = −46, well behind the building, while a `uScale` uniform grows its body by exactly
the ratio of its new camera distance to the one it had while it was the subject — so
its size on screen never changes, only its depth. That reference distance and the
framing radius are both frozen while the cloud is the subject, so its own growth
cannot feed back into the camera. Presence is carried by tone alone: the points drop
to 45 % as the focus rises. A first pass at 14 % was too far — the cloud read as a
small bright core rather than a mass standing behind.

"转换节奏太拖沓了 … 3s内我需要粒子团产生第一次明显的呼吸形变来抓人眼球，可以把呼吸的
下阈值拉高": the cycle came down from thirty-five seconds to twenty-five — the cloud
is whole by 1.6 s, the frames are on it by 3.2 s, the building starts at 6 s and takes
three seconds a layer. And the breath now shows. It has a floor (0.32, and it answers
the music one and a half times as strongly and twice as fast), it deforms the *shape*
rather than the area — the body draws up tall and narrow when the passage is quiet and
settles wide and low when it fills — and the arrival carries one scripted swing of its
own, a sine over the first two and a half seconds, so the mass is seen to breathe
before the music has had a chance to.

"分析框不要贸然出现，要缓慢出现 … 喷洒的粒子簇 … 和粒子云还是割裂的 … 粒子的着色需要
更有层次 … 分析框的绘制有点太简陋了，要精修 … 粒子簇是粒子云的subset，不要喧宾夺主":
four corrections, all about weight. The frames arrive over four seconds instead of
one, and each one now fades to its place and away again on its own eased visibility
rather than switching on the frame its band crosses the threshold. They are drawn as
a survey draws them: a hairline rectangle, crisp brackets at the four corners, a small
cross at the centre, and a caption that is an index, a rule and a stem rather than a
filled plate. The flying dust wears the cloud's own lilac and pale blue and is as
quiet as it — the white spark marks only the landing — and the settled points are
half the size and half the weight they were, in colours parted from the cloud's just
enough to tell the layers apart: the building is a subset of the mass, not a rival to
it. And the cloud has relief at last: each point knows how deep in the body it sits,
and lifts its colour, its size and its weight accordingly, so the dense parts stand
out of the haze instead of everything reading as one flat veil.

"边框 … 太淡了，几乎与粒子云同色 … 连线不要连在框的中心，把进入框内的那段截掉 … 粒子云
渐隐后的闪烁效果看起来像是打雷": the survey became its own instrument layer — warm
amber, not the cloud's lilac, each line carrying a dark halo so it holds over the
mass. Its net is clipped to the frames: for each run the parameter at which it leaves
one rectangle and enters the other is solved, and the line is drawn only between
those points with a three-pixel gap, so it meets an edge and never crosses a frame or
reaches a centre. And the lightning is gone: the white the core mixed toward is now a
pale blue at a fifth of its former weight, and the per-particle shake and the treble
fizz tick at nine and seven times a second instead of twenty-two and twelve, below
the rate at which additive points read as a strobe.

"粒子云渐隐但是不缩小 … 该在屏幕上多大就多大 … 屏幕半径使用0.5": measured, the first
attempt failed — the compensation had been applied to the *simulation*, and the
springs could not chase a camera pulling back over four seconds, so the apparent
radius fell from 0.40 to 0.18 and never recovered. It is now applied at the draw and
solved rather than remembered: each frame the body's ninety-second-percentile radius
is measured off the read-back, and the point shader enlarges the body about its own
centre by whatever factor makes it subtend a fixed angular radius of 0.5 — a little
over one and a half times the half-height of the view, so it always overflows the
frame. Measured across a cycle it holds between 0.495 and 0.54, dipping to 0.42 only
in the second when the camera moves fastest.

## The first design, and why it went

The first strip (`SoundStrip.tsx`, now deleted) was a player: decoded waveform, live
LED spectrum with peak-hold caps, a spectrogram painted under the playhead as the track
played, a Joy Division ridgeline on the compile face, a beat-locked pulse on the play
button, and the part readout changing as the playhead crossed each segment. It was
built from a survey of the best of its kind on GitHub, and every one of those borrowings
was good at what it did:

| Source | Borrowed then | Status now |
|---|---|---|
| [hvianna/audioMotion-analyzer](https://github.com/hvianna/audioMotion-analyzer) | peak-hold caps, LED bars, Hz scale | retired — a live meter says "happening now" |
| [katspaugh/wavesurfer.js](https://github.com/katspaugh/wavesurfer.js) | bar waveform, hover cursor with timestamp, timeline notches | the hover cursor's idea survives as the measure hover; the waveform is gone |
| [googlecreativelab/chrome-music-lab](https://github.com/googlecreativelab/chrome-music-lab) (Spectrogram) | log-frequency spectrogram on the track's own time axis | survives only as the *hearing* — raw material for the entrance and the hover, never on screen at rest |
| "Lines" via [willianjusten/awesome-audio-visualization](https://github.com/willianjusten/awesome-audio-visualization) | the Joy Division ridgeline | retired |
| [zachwinter/kaleidosync](https://github.com/zachwinter/kaleidosync) | motion locked to analysed beats | retired — the one thing the building must not seem to do |

The user's judgment, which decided it: playback has no relationship to the building,
the *analysis* does; a moving timeline contradicts "architecture is frozen music" and
misleads a viewer into thinking the form follows the sound. Both are right, and the
second design is the first one's measurements without its motion.
