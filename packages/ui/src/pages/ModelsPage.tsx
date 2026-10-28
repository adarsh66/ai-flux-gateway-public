import { useSession } from "../session";
import { AsyncView, Badge, PageHeader, useAsync } from "../components/ui";
import { DeploymentStatus } from "../components/DeploymentStatus";
import { DisplayPriceDetails } from "../components/DisplayPrice";

export function ModelsPage() {
  const { api } = useSession();
  const state = useAsync(async () => {
    const [models, garden] = await Promise.all([api.models(), api.modelGarden()]);
    return { ...models, items: models.items.map(m => ({ ...m, display_price: garden.items.find(g => g.id === m.id)?.display_price })) };
  }, [api]);
  return (
    <>
      <PageHeader title="Model catalog" subtitle="Verified deployed chat models with accepted gateway routes." />
      <AsyncView state={state} isEmpty={(d) => d.items.length === 0} emptyTitle="No models are enabled" emptyHint="IDS has not published any enabled models yet. Contact your IDS representative.">
        {(d) => (
          <ul className="cards" aria-label="Model availability">
            {d.items.filter((m) => m.enabled && !m.placeholder && m.capabilities.includes("chat")).map((m) => (
              <li className="card" key={m.id}>
                <h2>{m.id}</h2>
                <p>{m.provider}</p>
                <DisplayPriceDetails price={m.display_price} />
                  <span className="badges">
                    {m.placeholder ? <Badge tone="warn">Preview only - not callable</Badge> : m.capabilities.length === 0 ? <span className="muted">None declared</span> : m.capabilities.map((c) => <Badge key={c} tone="info">{c}</Badge>)}
                  </span>
              </li>
            ))}
          </ul>
        )}
      </AsyncView>
      <DeploymentStatus />
    </>
  );
}