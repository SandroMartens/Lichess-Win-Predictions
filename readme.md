# Win Probabilities in chess

## Intro

In this notebook I want to show how you can calculate the win probability of a chess player given the engone evaluation of the position. This was to reproduce the numbers in [this](https://lichess.org/page/accuracy) post. Converting an engine evaluation to a winning chance is useful because it considers how effective humans convert a position compared to an engine.

Lichess calculates the winning chances using a logistic regression. The winning chance of the White player is calculated as $p(white\ win) = 50 + 50 * (2 / (1 + e ^ {(-0.00368208 * centipawns)}) - 1)$.

## Data

## Methods

## Results
