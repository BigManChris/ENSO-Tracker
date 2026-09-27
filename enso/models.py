"""Four forecasters with the same interface: fit(X, Y) then predict(X).

Y has one column per lead and may contain NaN (targets not yet observed);
each model only learns from the values that exist.

  Persistence  "tomorrow looks like today": the benchmark to beat.
  Analog       find the past months that looked most like now; average what
               happened next.
  Ridge        a regularised linear regression per lead.
  NeuralNet    a small bagged neural network (scikit-learn MLP). There are
               only ~550 training months, so it's kept tiny and heavily
               regularised, and 10 copies trained on resampled data are
               averaged to calm it down.
"""

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

RONI_NOW = 0  # column of the current RONI in the feature matrix
ANALOG_COLS = [0, 3, 5, 9, 11, 13, 14]  # RONI now/3mo, Niño3.4, Niño4, heat, heat change
MONTH_COLS = (15, 16)


class Persistence:
    name = "Persistence"

    def fit(self, X, Y):
        return self

    def predict(self, X):
        return np.repeat(X[:, [RONI_NOW]], self.leads, axis=1)

    def __init__(self, leads):
        self.leads = leads


class Analog:
    name = "Analog"

    def __init__(self, k=12):
        self.k = k

    def fit(self, X, Y):
        self.scaler = StandardScaler().fit(X[:, ANALOG_COLS])
        self.Z = self.scaler.transform(X[:, ANALOG_COLS])
        self.month = np.round(np.arctan2(X[:, MONTH_COLS[0]], X[:, MONTH_COLS[1]]) / (2 * np.pi) * 12) % 12
        self.Y = Y
        return self

    def predict(self, X):
        Z = self.scaler.transform(X[:, ANALOG_COLS])
        mon = np.round(np.arctan2(X[:, MONTH_COLS[0]], X[:, MONTH_COLS[1]]) / (2 * np.pi) * 12) % 12
        out = np.full((len(X), self.Y.shape[1]), np.nan)
        for i, (z, m) in enumerate(zip(Z, mon)):
            # Only compare with the same time of year (+/- 1 month): ENSO is seasonal.
            gap = np.abs((self.month - m + 6) % 12 - 6)
            cand = np.where(gap <= 1)[0]
            dist = np.sqrt(((self.Z[cand] - z) ** 2).sum(axis=1))
            for lead in range(self.Y.shape[1]):
                ok = cand[~np.isnan(self.Y[cand, lead])]
                dl = dist[~np.isnan(self.Y[cand, lead])]
                if len(ok) == 0:
                    continue
                best = np.argsort(dl)[: self.k]
                w = 1 / (dl[best] + 0.1)
                out[i, lead] = np.sum(w * self.Y[ok[best], lead]) / w.sum()
        return out


class _PerLead:
    """Fit one scikit-learn regressor per lead on the rows where that lead is known."""

    def make(self, lead):
        raise NotImplementedError

    def fit(self, X, Y):
        self.scaler = StandardScaler().fit(X)
        Z = self.scaler.transform(X)
        self.models = []
        for lead in range(Y.shape[1]):
            ok = ~np.isnan(Y[:, lead])
            self.models.append(self.make(lead).fit(Z[ok], Y[ok, lead]))
        return self

    def predict(self, X):
        Z = self.scaler.transform(X)
        return np.column_stack([m.predict(Z) for m in self.models])


class LinearModel(_PerLead):
    name = "Ridge"

    def make(self, lead):
        return Ridge(alpha=10.0)


class _BaggedMLP:
    def __init__(self, n_models, seed):
        self.n_models, self.seed = n_models, seed

    def fit(self, Z, y):
        rng = np.random.default_rng(self.seed)
        self.nets = []
        for i in range(self.n_models):
            idx = rng.integers(0, len(Z), len(Z))  # bootstrap resample
            net = MLPRegressor(hidden_layer_sizes=(16,), activation="tanh",
                               alpha=1.0, learning_rate_init=0.01,
                               max_iter=800, random_state=self.seed + i)
            self.nets.append(net.fit(Z[idx], y[idx]))
        return self

    def predict(self, Z):
        return np.mean([n.predict(Z) for n in self.nets], axis=0)


class NeuralNet(_PerLead):
    name = "Neural net"

    def __init__(self, n_models=10, seed=0):
        self.n_models, self.seed = n_models, seed

    def make(self, lead):
        return _BaggedMLP(self.n_models, self.seed + 100 * lead)


def all_models(leads, n_nets=10):
    return [Persistence(leads), Analog(), LinearModel(), NeuralNet(n_nets)]


ENSEMBLE_OF = ("Analog", "Ridge", "Neural net")
