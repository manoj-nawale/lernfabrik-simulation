import random
import itertools

def _should_stop(env, stop_at):
    """Return True if a cutoff is set and the sim time has reached/passed it."""
    return (stop_at is not None) and (env.now >= stop_at)

def new_orders_source(env, cfg, buffers, metrics, stop_at=None):
    """
    Generate 'new' items into neu_lager using a Poisson process.
    Poisson arrivals => exponential interarrival times with mean 1/rate.

    If stop_at is provided (in minutes), no NEW arrivals will be created at/after that time.
    """
    rate = cfg["arrivals"]["new_orders"]["rate_per_min"]
    counter = itertools.count(1)

    while True:
        # stop injecting if we've reached the cutoff
        if _should_stop(env, stop_at):
            break

        # draw next interarrival (minutes)
        inter = random.expovariate(rate) if rate > 0 else 10**9

        # if the next arrival would cross the cutoff, advance to cutoff and stop
        if stop_at is not None and env.now + inter > stop_at:
            yield env.timeout(max(0, stop_at - env.now))
            break

        yield env.timeout(inter)

        token = {
            "id": f"NEW-{next(counter):05d}",
            "type": "new",
            "t_created": env.now,
        }

        # try to put into neu_lager (respect capacity)
        neu = buffers["neu_lager"]
        if len(neu.items) < neu.capacity:
            yield neu.put(token)
            metrics["arrivals_new"] += 1
        else:
            metrics["lost_new_due_to_neu_lager_full"] += 1


def returns_source(env, cfg, buffers, metrics, stop_at=None):
    """
    Batched returns: every ~interarrival_min, create a batch with mean batch_mean.
    If stop_at is provided (in minutes), no RETURNS are created at/after that time.
    """
    inter = cfg["arrivals"]["returns"]["interarrival_min"]
    batch_mean = cfg["arrivals"]["returns"]["batch_mean"]
    i = 0

    while True:
        if _should_stop(env, stop_at):
            break

        dt = random.expovariate(1.0 / inter)
        if stop_at is not None and env.now + dt > stop_at:
            yield env.timeout(max(0, stop_at - env.now))
            break

        yield env.timeout(dt)

        # ~ batch_mean ± 1 (keep at least 1)
        batch_size = max(1, int(random.gauss(batch_mean, 1)))

        for _ in range(batch_size):
            i += 1
            token = f"RET-{i:05d}"
            yield buffers["warenannahme"].put(token)
            metrics["arrivals_returns"] += 1
