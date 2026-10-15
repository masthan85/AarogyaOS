/**
 * Turns a page of HTML into a PDF on the phone (using its own fonts, so every Indian script
 * renders) and opens the share sheet. Nothing is uploaded; the file sits in the cache until the OS
 * clears it. Never run on a device in this repository's build environment.
 */
export async function sharePdf(html: string, title: string): Promise<void> {
  // Loaded lazily: these native modules do not exist under Jest or on web.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const Print = require('expo-print');
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const Sharing = require('expo-sharing');
  const { uri } = await Print.printToFileAsync({ html });
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(uri, { mimeType: 'application/pdf', dialogTitle: title, UTI: 'com.adobe.pdf' });
  } else {
    await Print.printAsync({ uri });
  }
}

export async function printHtml(html: string): Promise<void> {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  await require('expo-print').printAsync({ html });
}
