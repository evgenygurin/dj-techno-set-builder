# Research Prompt for Claude Opus 4.6

## Task: Deep Research on Techno DJ Set Construction

You are tasked with comprehensive research on creating professional-quality techno DJ sets using algorithmic approaches. This research will inform the development of an AI-powered DJ set generator.

---

## Context

We have a system that analyzes techno tracks and extracts detailed audio features:
- **Tempo**: BPM, stability, tempo confidence
- **Energy**: 6 frequency bands (sub, low, low-mid, mid, high-mid, high), ratios, slopes
- **Spectral**: centroid, rolloff, flatness, flux, contrast, harmonic-to-noise ratio
- **Rhythm**: onset rates, pulse clarity, kick prominence, hat/percussion ratio
- **Harmony**: key detection (24 keys), Camelot wheel compatibility, chroma vectors
- **Loudness**: LUFS (integrated, short-term, momentary), dynamic range
- **Structure**: intro/breakdown/buildup/drop/bridge/outro sections with timing

**Current approach**: Genetic algorithm optimizing:
1. Transition quality (50%) — primitive BPM + key distance
2. Energy arc adherence (30%) — target curve matching
3. BPM smoothness (20%) — penalize tempo jumps

**Problem**: We use <5% of available data. Transition quality is primitive.

---

## Research Objectives

### 1. DJ Theory & Practice

**Investigate:**
- How do professional techno DJs select track order?
- What makes a "good transition" vs "bad transition"?
- Key mixing rules: Camelot wheel, energy levels, phrase alignment
- Mixing techniques: beatmatching, EQ blending, frequency masking
- Set structure: intro → warm-up → peak → breakdown → second peak → outro
- Genre-specific considerations for techno (minimal, peak-time, industrial, etc.)

**Sources to search:**
- DJ forums (Resident Advisor, r/DJs, r/Beatmatch)
- DJ education resources (Crossfader, DJ TechTools, Point Blank)
- Mixing tutorials (YouTube, MasterClass)
- Books: "How to DJ Right" (Bill Brewster), "Last Night a DJ Saved My Life"
- Rekordbox, Traktor, Serato documentation on analysis features

**Deliverable**: Principles of techno set construction with evidence/citations

---

### 2. Audio Features for Transition Quality

**Investigate:**
- Which audio features predict mix compatibility?
  - Harmonic mixing: Camelot wheel effectiveness, key confidence thresholds
  - Energy matching: which frequency bands matter most for techno?
  - Spectral similarity: centroid vs rolloff vs contrast — which correlates with "sounds similar"?
  - Rhythmic compatibility: kick prominence, pulse clarity, groove matching
  - Loudness: LUFS matching, dynamic range considerations

**Research questions:**
- Do spectral features predict "smooth mix" better than energy features?
- Is kick prominence matching critical for techno (vs other genres)?
- How important is LUFS matching vs perceived energy?
- Does BPM stability affect mix-in/mix-out points?

**Sources to search:**
- Music Information Retrieval (MIR) papers
- Automatic DJ research: "AutoMix", "Intelligent DJ", "Playlist Generation"
- Academic databases: arXiv, IEEE, ACM Digital Library
- GitHub: DJ automation projects, music analysis libraries
- Spotify/Apple Music playlist algorithm patents

**Deliverable**: Ranked list of features by importance with research backing

---

### 3. Transition Scoring Algorithms

**Investigate:**
- Existing approaches to quantify transition quality
- Multi-objective optimization for set generation
- Distance metrics for audio similarity:
  - Euclidean vs Cosine vs Mahalanobis for feature vectors
  - Perceptual weighting of features
- Temporal aspects:
  - Optimal mix duration (4 bars, 8 bars, 16 bars?)
  - Phrase alignment (where to start/end mix)
  - Using structure sections (intro/outro) for mix points

**Research questions:**
- What's the state-of-the-art transition scoring formula?
- Do ML models outperform rule-based scoring?
- How to combine multiple objectives (harmonic + energy + spectral)?
- Is there research on "optimal mix point detection"?

**Sources to search:**
- "Automatic playlist continuation" papers
- "Music similarity" research
- DJ software analysis features documentation
- Music recommendation algorithms (collaborative filtering vs content-based)

**Deliverable**: Transition scoring formula recommendations with trade-offs

---

### 4. Set Generation Algorithms

**Investigate:**
- Approaches to sequence optimization:
  - Genetic Algorithms (current approach)
  - Simulated Annealing
  - Reinforcement Learning
  - Constraint Satisfaction
  - Graph algorithms (TSP-like formulations)
- Multi-objective optimization:
  - Pareto fronts for competing goals
  - Weighted vs lexicographic approaches
- Comparison: which algorithm works best for set generation?

**Research questions:**
- Is GA optimal or are there better algorithms?
- How to handle multiple conflicting objectives?
- Can RL learn from user feedback over time?
- Graph-based: treating transitions as edges, quality as weights

**Sources to search:**
- Operations research: Traveling Salesman Problem variants
- Recommender systems: sequence-aware recommendation
- "Music playlist generation" academic papers
- AI papers on sequential decision making
- GitHub: open-source DJ automation, playlist generators

**Deliverable**: Algorithm comparison with pros/cons for DJ sets

---

### 5. Energy Arc Patterns

**Investigate:**
- Typical techno set energy curves:
  - Warm-up set structure
  - Peak-time set structure
  - Closing set structure
- Mathematical models for energy progression
- Adaptive energy arcs based on track pool
- Multi-peak vs single-peak structures

**Research questions:**
- Are there genre-specific energy arc templates?
- How to model "energy" from multi-dimensional features?
- Should energy arc be fixed or adaptive to available tracks?
- What about "valleys" (breakdown sections) in energy?

**Sources to search:**
- DJ mix analysis (Mixcloud, SoundCloud tracklists with timestamps)
- Set structure discussions on forums
- Live recording analysis tools
- Academic papers on "music dynamics" or "tension/release"

**Deliverable**: Energy arc templates with techno-specific patterns

---

### 6. Mix Point Detection

**Investigate:**
- How to identify optimal mix-in and mix-out points
- Using structure sections (intro/outro detection)
- Beat/phrase alignment
- Frequency content analysis for "safe zones"
- Loop points for waiting

**Research questions:**
- Can intro/outro be detected reliably from structure analysis?
- What makes a "good mix point" — low complexity? specific energy?
- How long should transitions be? (genre-dependent?)
- Detecting "breakdown" sections for effect opportunities

**Sources to search:**
- Beatmatching algorithms
- Structure analysis research (music segmentation)
- DJ software features: hot cues, loop markers
- Music theory: phrase structure, bar counts

**Deliverable**: Algorithm for mix point detection from our structure data

---

### 7. Real-World Examples & Case Studies

**Investigate:**
- Analyze famous techno sets (Ben Klock, Marcel Dettmann, Amelie Lens)
- Extract patterns:
  - BPM progression
  - Key changes
  - Energy flow
  - Track selection logic
- Compare algorithmic sets to human-curated ones

**Sources to search:**
- Mixcloud/SoundCloud with tracklists
- RA podcasts with track IDs
- Discogs: DJ mix releases
- YouTube: Boiler Room, Cercle, HÖR sets with timestamps

**Deliverable**: Patterns observed in pro sets vs our algorithm output

---

### 8. Evaluation Metrics

**Investigate:**
- How to measure set quality objectively?
  - Transition smoothness metrics
  - Energy arc coherence
  - Harmonic flow
  - Variety vs cohesion balance
- User study designs for subjective evaluation
- A/B testing methodologies

**Research questions:**
- What metrics correlate with human preference?
- Can we predict "crowd energy" from features?
- How to evaluate without extensive user testing?

**Sources to search:**
- Music recommendation evaluation methods
- User experience research in music apps
- DJ community feedback on auto-generated playlists

**Deliverable**: Evaluation framework for set quality

---

### 9. Edge Cases & Constraints

**Investigate:**
- Handling variable BPM tracks
- Atonal/experimental techno
- Tracks with key changes mid-song
- Unreliable feature detection (low confidence)
- Genre boundaries (techno → minimal → tech-house)

**Research questions:**
- How to weight low-confidence features?
- Should we filter out "hard to mix" tracks?
- Can we detect genre drift in a set?

**Deliverable**: Edge case handling strategies

---

### 10. Tools & Libraries

**Investigate:**
- Existing open-source DJ tools:
  - Essentia (audio analysis)
  - librosa (MIR in Python)
  - Sonic Annotator
  - DJing libraries: transitions.py, etc.
- Commercial tools:
  - Mixed In Key
  - Rekordbox analysis
  - Traktor Pro
- Relevant research codebases on GitHub

**Deliverable**: Comparison of tools & libraries with integration potential

---

## Research Methodology

For each objective:
1. **Search comprehensively**:
   - Academic papers (arXiv, IEEE, ACM)
   - Technical blogs (Medium, dev.to)
   - DJ forums & communities
   - Documentation & tutorials
   - GitHub repositories
   - YouTube educational content

2. **Synthesize findings**:
   - Identify consensus approaches
   - Note conflicting opinions with rationale
   - Extract actionable recommendations
   - Cite sources for verification

3. **Prioritize insights**:
   - Quick wins (use existing data better)
   - Medium-term (compute new features)
   - Long-term (ML approaches)

---

## Output Format

For each of the 10 objectives above, provide:

### [Objective Title]

**Summary** (2-3 paragraphs):
- Key findings
- Consensus in the field
- Surprises or counterintuitive results

**Detailed Findings**:
1. [Finding 1 with source citations]
2. [Finding 2 with source citations]
...

**Actionable Recommendations**:
- ✅ **Quick win**: [what we can do now with existing data]
- 🔧 **Medium-term**: [what requires new computation/features]
- 🚀 **Long-term**: [advanced approaches requiring significant work]

**Sources**:
- [Author, Year, Title, Link]
- [Author, Year, Title, Link]
...

**Open Questions**:
- [Questions that remain unanswered and require further investigation or experimentation]

---

## Success Criteria

Research is complete when:
- ✅ All 10 objectives have detailed findings with citations
- ✅ At least 20 academic papers reviewed
- ✅ At least 10 practical resources (tutorials, forums, docs)
- ✅ Clear roadmap of improvements: quick wins → medium → long-term
- ✅ Specific formulas/algorithms recommended (not just concepts)
- ✅ Evidence-based prioritization of features

---

## Special Focus Areas

Given our current state, prioritize:
1. **Camelot wheel usage** — we have key_edges table but don't use it
2. **Energy band matching** — we have 6 bands but only use energy_mean
3. **TransitionScoringService design** — what should it compute?
4. **Mix point detection** — we have structure sections, how to use them?

Search specifically for:
- "Camelot wheel effectiveness" studies
- "Harmonic mixing research"
- "Energy matching in DJ transitions"
- "Automatic mix point detection"
- "DJ set energy curves"

---

## Constraints & Context

- **Genre focus**: Techno (minimal techno, peak-time techno, industrial)
- **Technical stack**: Python, essentia, librosa, SQLite/PostgreSQL, FastAPI
- **Current bottleneck**: Primitive transition scoring
- **Goal**: Professional-quality algorithmic sets that match or exceed human DJs for "filler sets" (warm-up, background)

---

## Expected Timeline

- **Initial research**: 2-3 hours (broad sweep)
- **Deep dive**: 4-6 hours (detailed investigation)
- **Synthesis**: 1-2 hours (compile findings)
- **Total**: ~8 hours of focused research

---

## Deliverable Format

Single comprehensive document addressing all 10 objectives with:
- Executive summary (1 page)
- Detailed findings per objective (50+ pages)
- Appendix: Full source list with links
- Appendix: Recommended formulas & algorithms
- Appendix: Prioritized implementation roadmap

---

## Additional Notes

- Emphasize **evidence-based** recommendations (cite sources!)
- Include **code examples** where available (GitHub links)
- Note **conflicting opinions** in the field with reasoning
- Provide **quantitative comparisons** where possible (Algorithm A vs B performance)
- Consider **computational cost** of recommendations (real-time vs batch)

---

## Go!

Begin comprehensive research. Take your time. Be thorough. Cite sources. Surprise me with insights I didn't know to ask for.
