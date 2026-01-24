import click
import os


@click.command()
@click.argument("source", type=click.Path(exists=True))
@click.argument("target", type=click.Path())
@click.option("--ignore", "-i", multiple=True)
def snip(source: str, target: str, ignore: tuple[str, ...]):
    if os.path.exists(".snipignore"):
        with open(".snipignore", "r") as f:
            ignore += tuple(l.strip() for l in f.readlines())

    _snip_element(source, target, ignore)


def _snip_element(source: str, target: str, ignore: tuple[str, ...]):
    if any(os.path.samefile(ig, source) for ig in ignore if os.path.exists(ig)):
        return

    if os.path.isdir(source):
        _snip_directory(source, target, ignore)
    else:
        _snip_file(source, target)


def _snip_directory(source: str, target: str, ignore: tuple[str, ...]):
    if not os.path.exists(target):
        os.makedirs(target)
    elif not os.path.isdir(target):
        raise ValueError(f"{target} is not a directory")

    for elem in os.listdir(source):
        _snip_element(os.path.join(source, elem), os.path.join(target, elem), ignore)


def _snip_file(source: str, target: str):
    print("snipping", source, "to", target)
    with open(source, "r") as f:
        lines = f.readlines()

    writing = True

    with open(target, "w") as f:
        for line in lines:
            if "# " "<<" in line:
                line = line.replace("# " "<<", "")
            if "----" "8<----" in line:
                writing = not writing
            elif writing:
                f.write(line)


if __name__ == "__main__":
    snip()
