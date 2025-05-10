export function tranformHankakuToZenkaku(str: string): string {
  return str.replace(/[A-Za-z0-9]/g, function (s) {
    return String.fromCharCode(s.charCodeAt(0) + 0xfee0);
  });
}
