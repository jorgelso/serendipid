import PaperTicket from "./PaperTicket";

export default function ScrapbookMasthead({ subtitle }: { subtitle: string }) {
  return (
    <div className="relative mb-3" style={{ height: 190 }}>
      <PaperTicket kind="mag" left={0} top={0} width={230} height={92} fontSize={54} color="#161207" maskColor="var(--color-yellow)" rotation={-4} z={2}>
        Study
      </PaperTicket>
      <PaperTicket kind="foil" left={215} top={38} width={230} height={86} fontSize={44} rotation={3} z={3}>
        Guides
      </PaperTicket>
      <PaperTicket kind="hand" left={455} top={26} width={340} fontSize={17} color="#221a12" rotation={-1} z={1}>
        {subtitle}
      </PaperTicket>
    </div>
  );
}
