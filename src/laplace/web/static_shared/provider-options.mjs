// Passive catalogue choices shared by conversation and review setup. No selection, I/O or preferences.
export const providerModelOptions=provider=>provider?.models||[];
export function providerEffortOptions(model){return model?.supports_effort===false?['medium']:(model?.efforts?.filter(Boolean)?.length?model.efforts.filter(Boolean):['low','medium','high']);}
