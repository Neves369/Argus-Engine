interface CardProps {
  image?: string;
  burning?: boolean;
  burnSide?: 'left' | 'right' | 'center';
  appearing?: boolean;
}

function Card({
  image,
  burning = false,
  burnSide = 'center',
  appearing = false,
}: CardProps) {
  const sideClass = burning ? ` card-burn-${burnSide}` : '';

  return (
    <div
      className={`card${burning ? ' is-burning' : ''}${sideClass}${appearing ? ' is-appearing' : ''}`}
      style={image ? { backgroundImage: `url(${image})` } : undefined}
    />
  );
}

export default Card;
