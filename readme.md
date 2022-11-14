# Win Probabilities in chess using centipawns

## Intro

In this notebook I want to show how you can calculate the win probability of a chess player given the engone evaluation of the position. This was to reproduce the numbers in [this](https://lichess.org/page/accuracy) post. Converting an engine evaluation to a winning chance is useful because it considers how effective humans convert a position compared to an engine.

Lichess calculates the winning chances using a logistic regression. The winning chance of the White player is calculated as $p(white\ win) = 50 + 50 * (2 / (1 + e ^ {(-0.00368208\ *\ centipawns)}) - 1)$.

The blogpost claims the exponent is based on real game data. So I downloaded a bunch of pro games and decided to try to reproduce this number. I analyzed over 1000 games with stockfish and calculated an exponent of $0.0028322$ to solve the logistic regression.

## Data

I analyzed games from the [Lichess Elite Database](https://database.nikonoel.fr/) from April 2022.

## Methods

The games were parsed and each position fen written in to a database. I then used [Stockfish 15](https://stockfishchess.org/) to evaluate the positions. As search limit was set to three million nodes. This is more than the Lichess server analysis but still runs good on a normal PC.

For the next step I used [scikit-learn](https://scikit-learn.org/stable/index.html). 

## Results
