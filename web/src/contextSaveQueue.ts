export type NavigationGuard = () => Promise<boolean>;

export class ContextSaveQueue {
  private tail: Promise<void> = Promise.resolve();
  private failures = new Map<string, Error>();
  private outstanding = 0;

  get pending() {
    return this.outstanding > 0;
  }

  get error(): Error | undefined {
    return this.failures.values().next().value;
  }

  retry(key: string) {
    this.failures.delete(key);
  }

  enqueue<T>(key: string, operation: () => Promise<T>): Promise<T> {
    this.outstanding += 1;
    const result = this.tail.then(operation);
    this.tail = result.then(
      () => { this.failures.delete(key); },
      (caught: unknown) => {
        this.failures.set(key, caught instanceof Error ? caught : new Error("Save failed."));
      },
    ).finally(() => { this.outstanding -= 1; });
    return result;
  }

  async flush(): Promise<void> {
    let tail: Promise<void>;
    do {
      tail = this.tail;
      await tail;
    } while (tail !== this.tail);
    if (this.error) throw this.error;
  }
}
