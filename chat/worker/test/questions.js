// Sample technical questions. `expect` matches text that must appear in a retrieved document
// (and, in the live check, in the answer). No `expect` means the data can't answer it.
export const EVAL = [
  { q: "How many ground signals did ILSA list with no known cause?", expect: /114 no known cause/ },
  { q: "What was the strongest moonquake signal on 26 August?", expect: /437\.6/ },
  { q: "How hot did the soil get at 4 mm depth?", expect: /67\.9|68 °C/ },
  { q: "What are the depths of the ChaSTE thermometers?", expect: /4, 10, 16, 22, 28, 36, 46, 63, 81, 98/ },
  { q: "Why doesn't the project reproduce ISRO's -10 °C at 80 mm?", expect: /−5|-5/ },
  { q: "What was the temperature gradient in the regolith?", expect: /3\.9 to 6\.8/ },
  { q: "How many APXS soil measurements did the rover make?", expect: /23/ },
  { q: "Which APXS stop is the odd one out for magnesium?", expect: /obs26_mob42_20230901/ },
  { q: "Did APXS detect sulphur?", expect: /[Ss]ulphur/ },
  { q: "What elements does the LIBS stack show?", expect: /[Mm]agnesium, oxygen, aluminium and silicon/ },
  { q: "What electron temperature did RAMBHA-LP measure?", expect: /5,300–7,500 K|electron temperature/ },
  { q: "How was the ChaSTE probe inserted into the soil?", expect: /2\.65 mm steps|102 steps/ },
  { q: "What happened on 3 September?", expect: /hop/i },
  { q: "How typical is the shaking from the rover driving?", expect: /rover driving 265\.5 µg/ },
  { q: "What problems did you find in the ChaSTE archive files?", expect: /3,248 records/ },
  { q: "How is the Sun's height at the landing site computed?", expect: /operations table/ },
  { q: "What was the plasma density on aug 30?", expect: /Data for 30 August[\s\S]*|electron density/ },
  { q: "What is the capital of France?" },
  { q: "Tell me about the Mars Orbiter Mission Mangalyaan", llm: true },
  { q: "Who won the cricket world cup?" },
];
