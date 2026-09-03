---
title: "Three projects, one lesson: almost every number I published was inflated"
published: false
tags: machinelearning, python, mlops, datascience
---

I trained a classifier for 100 Ecuadorian species, built a pipeline to watch it
work on real observations, and put an agent on top. Three repos, about three
months.

This post isn't about how I built them. It's about how **every time I measured
something properly, the number went down** — and how that's the job, not a
setback.

Four cases. In all four the first number was defensible, published, and
misleading.

---

## The setup

Just enough to follow the rest:

| | |
|---|---|
| **[riksi](https://github.com/DiegoFernandoLojanTenesaca/riksi)** | EfficientNet-Lite0, 100 species, 3.8 MB in int8. Runs in the browser via ONNX Runtime Web |
| **[riksi-radar](https://github.com/DiegoFernandoLojanTenesaca/riksi-radar)** | Kafka → the model → DuckDB → dbt. Pulls new observations from [GBIF](https://www.gbif.org/) and classifies them without seeing the label |
| **[yachaq](https://github.com/DiegoFernandoLojanTenesaca/yachaq)** | An agent over all of it: RAG, memory, MCP server |

The model gets **79.8 %** top-1 on 1000 validation images. That one is measured
correctly and isn't among the numbers that fall apart.

---

## Case 1 · "The model does better outside its own split"

Validation images come from the same split as training: same sources, same
photographers, same framing bias. 79.8 % there answers a fairly narrow question.

So I built the radar: take observations uploaded to GBIF **afterwards**, by
different people, that nobody hand-picked, and run every photo through the model.

400 observations. **337 correct: 84.2 %.**

Six points above the validation bank. I wrote it in the README with "goes up" in
bold.

It's wrong. Not the arithmetic — the bias.

```
Amblyrhynchus cristatus (marine iguana)   128 of 400   32 %
top three species combined                198 of 400   50 %
distinct species, out of the 100 it knows          20
```

Citizen science doesn't sample uniformly. People photograph what they see, and in
the Galápagos they see marine iguanas. That 84.2 % is mostly the model's grade on
one species, repeated 128 times.

Averaging per species instead of per observation — giving the iguana the same
weight as the turtle that shows up three times:

| | accuracy |
|---|---|
| per observation | 84.2 % |
| **averaged over species** | **78.7 %** |

And there's the interesting part: **78.7 % in the field against 78.0 % on the
bank.** The model doesn't do better outside its split. It performs the same.

Which is a more boring conclusion and a far more credible one. "No drift" is a
result; "improves in production" was an artifact of how I averaged.

> If you're publishing one number over citizen-science data, average per class.
> The per-observation mean measures your data distribution as much as your model.

---

## Case 2 · The disagreements that weren't the model's fault

That left 63 observations where the model and GBIF disagreed. Three possible
explanations: the model was wrong, the observation is misidentified, or the photo
doesn't show what the record claims.

I wrote in the README that the pipeline doesn't decide which, and that the
Galápagos tortoises showing up repeatedly were "taxonomy disputed among
biologists."

I made that up. It sounded plausible and I never checked.

Turns out there's a fourth explanation, and it's checkable: **GBIF publishes
periodic snapshots, not a live mirror of iNaturalist.** An observation iNaturalist
already corrected can still sit in GBIF under the old identification.

You verify it in two hops. GBIF stores the iNaturalist identifier in
`catalogNumber`, so you can ask what the identification is **today**:

```python
def _en_inaturalist(clave_gbif):
    oc = _pedir(f"{GBIF}/occurrence/{clave_gbif}")
    id_inat = oc.get("catalogNumber")          # the link back to the source
    d = _pedir(f"{INAT}/observations/{id_inat}")
    o = d["results"][0]
    return {"taxon_hoy": (o.get("taxon") or {}).get("name"),
            "grado": o.get("quality_grade"),
            "identificaciones": o.get("identifications_count", 0)}
```

All 63, two minutes of requests. 24 carry a different label today.

But there's a trap I nearly walked into. Not every change means the same thing:

| change | what it is |
|---|---|
| `Anous stolidus` → `Anous stolidus galapagensis` | **refinement**: the population was narrowed down, the species is the same, the model was still wrong |
| `Chelonoidis porteri` → `Chelonoidis niger porteri` | **a different species**: it now hangs under *C. niger* |

In the second case the model had said `Chelonoidis niger`. Under today's
taxonomy, it was **right**. The Santa Cruz tortoise became a subspecies of *C.
niger* and GBIF still had the previous version.

Counting those separately is the whole difference between a finding and
self-deception, so the judging logic is the one piece with a real test:

```python
def _juzgar(caso, hoy):
    gbif, dice, ahora = caso["gbif"], caso["modelo"], hoy["taxon_hoy"]
    if ahora == gbif:                          return "unchanged"
    if _es_hijo(ahora, gbif):                  return "narrowed"
    if ahora == dice or _es_hijo(ahora, dice):  return "the model was right"
    return "species changed"
```

`_es_hijo` compares word by word rather than with `startswith`, which would
accept a match halfway through a word:

```python
assert not _es_hijo("Anous stolidusa", "Anous stolidus")
assert not _es_hijo("Anous stolidus", "Anous stolidus")   # nor its own child
assert     _es_hijo("Chelonoidis niger porteri", "Chelonoidis niger")
```

The result:

| of the 63 disagreements | |
|---|---|
| label unchanged | 39 |
| narrowed to subspecies → still wrong | 16 |
| **label was stale: the model was right** | **8** |

Eight out of 63 weren't errors. And all 63 are *research grade* on iNaturalist —
identifications the community already confirmed — so the other 55 have nowhere to
hide.

**And it still needs discounting.** All eight are the same taxon. Removing them
lifts the per-species mean from 78.7 % to 81.2 %, but that fixes one species out
of twenty and none of the rest: it's the Case 1 bias coming back through another
door. The number I'd still publish is 78.7 %.

---

## Case 3 · The threshold I'd picked by eye

The agent has a RAG over the fact sheets for all 100 species. The usual question:
above what similarity is a retrieved sheet actually relevant?

I set 0.5. Round number, no reason behind it.

What you need to measure isn't the mean similarity, it's **whether the two
populations separate**: questions the corpus can answer versus questions it
can't. If their distributions overlap, no threshold is good — the number isn't
the problem.

They did separate, with a 0.075 gap between them. The midpoint lands on **0.44**,
not 0.5.

The bonus came from trying to shrink the index, which took 235 MB:

```
vocabulary    disk     gap between the two populations
   250,037    235 MB    +0.075   ← the current one
   200,000    204 MB    +0.084   31 MB less; not worth the risk
   120,000    140 MB    THEY OVERLAP
    80,000    108 MB    THEY OVERLAP
    40,000     75 MB    +0.017   barely survives
```

Prune to 120,000 terms and the index gets 40 % smaller while **the threshold
stops existing**: there's no gap left to split. Without measuring the separation
that cut looks free — the system keeps answering, it just no longer knows when to
stay quiet.

---

## Case 4 · 671 MB in a 512 MB container

Not a measurement story, but the one that taught me most.

The agent had to fit a free tier: 512 MB. With `fastembed`, the process hit
**671 MB** just loading the encoder. Dead on arrival.

The cause: `fastembed` loads the model weights into RAM and keeps them there.

I rewrote inference by hand on ONNX Runtime. Two things fixed it. First, saving
the weights as external data, which gets them memory-mapped instead of copied:

```python
onnx.save(modelo, str(LIGERO / "modelo.onnx"), save_as_external_data=True, ...)

opciones = ort.SessionOptions()
opciones.enable_cpu_mem_arena = False      # no arena that grows and never returns
ort.InferenceSession(ruta, sess_options=opciones)
```

Second, releasing the session after each batch instead of holding it:

```python
def vectorizar(textos):
    with _candado:
        try:
            return _vectorizar(textos)
        finally:
            if SOLTAR:
                _sesion.cache_clear()
                gc.collect()
```

671 → 457 → **154 MB**, with room to spare.

Two traps along the way, both silent:

- **Mean pooling is weighted by the attention mask.** Average over the padding too
  and your vectors come out shifted. Nothing fails: the RAG just retrieves
  slightly worse results and you blame the model.
- **`enable_padding()` with no arguments pads to 512 tokens.** Inference that
  takes 0.2 s starts taking a minute. You need
  `direction="right", pad_id=1, pad_token="<pad>"`.

---

## What did work first try (not much)

So it doesn't read like everything collapsed:

- **int8 quantization** costs 0.4 top-1 points and takes the model from 13.5 to
  3.8 MB. Best trade in the project.
- **Averaging an image with its mirror** buys 0.2 points for double the response
  time. Measured, and **not implemented** — measuring to reject counts too.
- **LangGraph versus hand-rolled orchestration**: 95 statements against 55,
  31.0 s against 18.4 s. But LangGraph resumes from its checkpoint in 0.0 s and
  mine doesn't. With two nodes it isn't worth it; with fifteen and expensive work
  you don't want to repeat, it is. I kept mine and left the comparison in the
  repo.

---

## What I take from it

**A number that goes up is suspicious.** All four times a number pleased me, I
was measuring my dataset rather than my model.

**Average per class.** On citizen-science data, the per-observation mean is
nearly a description of which animals are photogenic.

**Check the anecdote that sounds good.** "Taxonomy disputed among biologists"
sounded like I knew what I was talking about. Two HTTP requests showed it was
false, and the truth turned out more interesting.

**Sort changes by kind before counting them.** 24 changed labels looked like 24
errors that weren't mine. It was 8. The other 16 were mine, dressed up as the
same thing.

**A threshold without a measured separation is decoration.** And if the system
still works with a useless threshold, nobody will ever find out.

---

## Future work

The honest part is saying where this doesn't reach:

- **400 observations and 20 species** say nothing about the other 80. The radar
  would need to run for weeks to have anything per species.
- **One model, one country.** None of this says whether the pattern holds
  anywhere else.
- **The iNaturalist check is a single day's snapshot.** Re-running it in six
  months would give GBIF's typical lag, which would be genuinely useful to anyone
  relying on that data.

All three repos are open, with the `--comprobar` self-checks behind the numbers:
[riksi](https://github.com/DiegoFernandoLojanTenesaca/riksi) ·
[riksi-radar](https://github.com/DiegoFernandoLojanTenesaca/riksi-radar) ·
[yachaq](https://github.com/DiegoFernandoLojanTenesaca/yachaq)
