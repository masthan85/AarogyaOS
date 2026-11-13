/** A stored code such as IN_CONSULTATION as words a person reads: "In consultation". */
export const sentence = (code: string): string => {
  const words = code.replace(/_/g, ' ').trim().toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
};
