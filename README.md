# Smart Order Router: Cont & Kukanov Static Cost Model

## 📌 Overview

This Smart Order Router (SOR) using the **Cont & Kukanov static cost model**. The goal was to optimize the execution of a 5,000-share buy order across multiple venues while minimizing total cost under market microstructure constraints.

Interestingly, the trial referenced a document titled `cont_kukanov_excerpt.pdf`, but I was not provided with this file. To ensure accuracy, I went through the full original paper to understand the model’s foundations and implement the router accordingly.

The router is benchmarked against:
- **Best Ask**: Immediate execution at best available prices
- **TWAP**: Time-weighted average price
- **VWAP**: Volume-weighted average price

---

## 🧠 Code Structure

The main logic is contained in `backtest.py`, structured as follows:

- **Snapshot Loader**: Cleans Level-1 data (`ask_px_00`, `ask_sz_00`) per timestamp and venue
- **Allocator**: Implements the static allocation model via exhaustive grid search
- **Cost Model**: Applies taker fees, maker rebates, and penalties for underfill, overfill, and queue impact
- **Fill Simulator**: Models slippage and partial fills per venue
- **Baselines**: Implements standard Best Ask, TWAP, VWAP strategies
- **Output**: Prints structured JSON result to stdout (suitable for automated eval)

> Only `numpy`, `pandas`, and optionally `matplotlib` (for plotting) are used.

---

## 🔍 Parameter Grid Search

The optimizer performs a grid search over three hyperparameters:

| Parameter        | Description                        | Range                        |
|------------------|-------------------------------------|------------------------------|
| `lambda_over`    | Overfill penalty                    | `np.linspace(0.0, 0.5, 11)`  |
| `lambda_under`   | Underfill penalty                   | `np.linspace(0.0, 1.0, 11)`  |
| `theta_queue`    | Queue position penalty sensitivity  | `np.linspace(0.0, 0.05, 11)` |

The best configuration is selected by minimizing total cash spent.

---

## 🧪 Fill Simulation and Realism

To introduce realism, I modeled venue-specific execution probabilities using a deterministic per-venue fill rate:

```python
fill_rate = 0.3 + 0.4 * ((venue_id % 5) / 4)
```

This creates consistency across runs while simulating diverse venue liquidity. I also included:
- **Partial fills** based on `fill_rate × size`
- **Maker rebates** for unfilled shares
- **Terminal underfill penalty** using `rem * 5.0` to encourage full completion

---

## 📊 Example Output

```json
{
  "best_params": {
    "lambda_over": 0.2,
    "lambda_under": 0.2,
    "theta_queue": 0.05
  },
  "tuned_router": {
    "total_spent": 1114137.48,
    "avg_price": 222.827
  },
  "best_ask": {
    "total_spent": 1114152.31,
    "avg_price": 222.830,
    "savings_bps": 0.13
  },
  "twap": {
    "total_spent": 1113833.57,
    "avg_price": 222.766,
    "savings_bps": -2.73
  },
  "vwap": {
    "total_spent": 1115545.81,
    "avg_price": 223.109,
    "savings_bps": 12.62
  }
}
```

---

## 🔧 Suggested Future Improvements

If given more time or data, I would expand this model to include **queue-depth estimation** using Level-1 field `ask_ct_00`:

```python
fill_rate = 1 / (1 + ask_ct_00)
```

This would model the likelihood of execution based on queue congestion and further improve realism. Another possible enhancement would be leveraging **Level-2 depth** via `ask_px_01` to `ask_px_09` for large order slicing across multiple price levels.

These additions would help capture microstructural effects like adverse selection and order book dynamics more effectively.


