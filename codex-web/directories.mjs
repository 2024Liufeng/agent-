import path from "node:path";
import os from "node:os";
import { realpath, readdir, stat } from "node:fs/promises";

let roots;
async function shortcuts(defaultPath) {
  if (!roots) {
    roots = (async () => {
      const candidates = [
        { name: "项目目录", path: path.dirname(defaultPath) },
        { name: "用户目录", path: os.homedir() },
        ...(process.platform === "win32"
          ? Array.from({ length: 24 }, (_, index) => {
              const drive = String.fromCharCode(67 + index);
              return { name: `磁盘 ${drive}:`, path: `${drive}:\\` };
            })
          : [{ name: "服务器", path: "/" }]),
      ];
      const available = await Promise.all(
        candidates.map(async (item) => {
          try {
            return (await stat(item.path)).isDirectory() ? item : null;
          } catch {
            return null;
          }
        }),
      );
      return available.filter(Boolean);
    })();
  }
  return roots;
}

export async function listDirectories(input, defaultPath) {
  const requested = input || path.dirname(defaultPath);
  if (!path.isAbsolute(requested)) throw new Error("请选择服务器上的绝对目录");
  try {
    const directory = await realpath(requested);
    const entries = await readdir(directory, { withFileTypes: true });
    const folders = await Promise.all(
      entries.map(async (entry) => {
        const entryPath = path.join(directory, entry.name);
        if (entry.isDirectory()) return { name: entry.name, path: entryPath };
        if (entry.isSymbolicLink()) {
          try {
            if ((await stat(entryPath)).isDirectory())
              return { name: entry.name, path: entryPath };
          } catch {}
        }
        return null;
      }),
    );
    const root = path.parse(directory).root;
    const breadcrumbs = [{ name: root, path: root }];
    let current = root;
    for (const name of directory
      .slice(root.length)
      .split(path.sep)
      .filter(Boolean)) {
      current = path.join(current, name);
      breadcrumbs.push({ name, path: current });
    }
    return {
      path: directory,
      parent: directory === root ? null : path.dirname(directory),
      entries: folders
        .filter(Boolean)
        .sort((a, b) =>
          a.name.localeCompare(b.name, "zh-CN", { numeric: true }),
        ),
      roots: await shortcuts(defaultPath),
      breadcrumbs,
    };
  } catch (error) {
    if (["EACCES", "EPERM"].includes(error.code))
      throw new Error("此目录无法访问，请返回上一级选择其他文件夹");
    if (["ENOENT", "ENOTDIR"].includes(error.code))
      throw new Error("目录不存在或已移动，请返回上一级重新选择");
    throw error;
  }
}
