import argparse
import configparser
import errno
import os
from pathlib import Path
import uuid
import boto3


CONFIG_FILE_DIRECTORY = fr'{os.path.expanduser("~")}\.config\cloudphoto\cloudphotorc\config.ini'
ALBUM_PREFIX = 'albums'
PHOTO_PREFIX = 'photos'
PHOTO_NAME_PREFIX = 'photos_name'

parser = argparse.ArgumentParser(description='Action')
parser.add_argument('action', type=str)
parser.add_argument('ALBUM', type=str, nargs='*')
parser.add_argument('--album', type=str, nargs='+')
parser.add_argument('--path', type=str)

args = parser.parse_args()
action = args.action


def read_cred_from_config():
    config = configparser.ConfigParser()
    config.read(f"{CONFIG_FILE_DIRECTORY}")
    not_found = []
    if 'DEFAULT' not in config:
        print("Error config file")
        exit(1)
    config_data = config["DEFAULT"]
    aws_access_key_id = config_data.get("aws_access_key_id", fallback=None)
    if aws_access_key_id is None:
        not_found.append("aws_access_key_id")

    aws_secret_access_key = config_data.get("aws_secret_access_key", fallback=None)
    if aws_secret_access_key is None:
        not_found.append("aws_secret_access_key")

    BUCKET = config_data.get("bucket", fallback=None)
    if BUCKET is None:
        not_found.append("bucket")

    region_name = config_data.get("region", fallback=None)
    if region_name is None:
        not_found.append("region")

    endpoint_url = config_data.get("endpoint_url", fallback=None)
    if endpoint_url is None:
        not_found.append("endpoint_url")

    if not_found:
        print(f"Not found next parameters:\n{not_found}\nPlease run init")
        exit(1)
    return aws_access_key_id, aws_secret_access_key, BUCKET, region_name, endpoint_url


def pre_init():
    ycls = boto3.session.Session(aws_access_key_id=aws_access_key_id,
                                 aws_secret_access_key=aws_secret_access_key,
                                 region_name=region_name)
    yclr = ycls.resource(service_name='s3', endpoint_url=endpoint_url)
    yclb = yclr.Bucket(BUCKET)
    return ycls, yclr, yclb


def upload():
    album_name = args.album
    album_name_str = ""
    if album_name is None:
        print(f"Not found next parameter: --album ALBUM")
        exit(1)

    l = len(album_name)
    for i in range(l):
        if i == l - 1:
            album_name_str += album_name[i]
        else:
            album_name_str += album_name[i] + " "

    photo_dir_path = args.path
    album_dict = get_list(True, False)
    if album_dict.get(album_name_str) is None:
        album_uuid = create_new_album(album_name_str)
    else:
        album_uuid = album_dict[album_name_str]

    if str(photo_dir_path).strip() == 'None':
        photo_dir_path = r'.'

    else:
        photo_dir_path = rf'{photo_dir_path}'

    files_path = Path(photo_dir_path)

    if not files_path.is_dir():
        print(f"Warning: No such directory <{photo_dir_path}>")
        exit(1)

    files = files_path.glob('*.jpg')
    files_list = []
    for f in files:
        files_list.append(f)

    files = files_path.glob('*.jpeg')
    for f in files:
        files_list.append(f)

    if not files_list:
        print(f"Warning: Photos not found in directory <{photo_dir_path}>")
        exit(1)

    for file in files_list:
        try:
            photo_uuid = create_new_photo(file.name, album_uuid)
            photo_key = f'{PHOTO_PREFIX}/{album_uuid}/{photo_uuid}'
            photo_object = admin_resource.Object(BUCKET, photo_key)
            photo_object.upload_file(file)
        except any:
            print(f'Warning: Photo not sent {file.name}')
            continue
    exit(0)


def download():
    album_name = args.ALBUM
    album_uuid = get_album_UUID(album_name)
    photo_dir_path = args.path

    if str(album_uuid) == 'None':
        print(f'Warning: Photo album not found <{str("".join(album_name))}>')
        exit(1)

    photo_dict_list = photo_dict(album_uuid)

    if str(photo_dir_path).strip() == 'None':
        photo_dir_path = r'.'

    else:
        photo_dir_path = rf'{photo_dir_path}'

    files_path = Path(photo_dir_path)

    if not files_path.is_dir():
        print(f"Warning: No such directory <{photo_dir_path}>")
        exit(1)

    for photo_info in photo_dict_list:
        photo_object = admin_resource.Object(BUCKET, f"{PHOTO_PREFIX}/{album_uuid}/{photo_info[0]}")
        photo_path = photo_dir_path + "\\" + photo_info[1]
        with open(photo_path, 'wb') as file:
            photo_object.download_fileobj(Fileobj=file)


def get_list(need_return, album_name_is_contains):
    album_dict = {}
    album_name = args.album

    for dir in admin_pub_bucket.objects.filter(Prefix=ALBUM_PREFIX):
        album_from_cloud_name = str(dir.get()['Body'].read().decode('utf-8'))
        album_dict[album_from_cloud_name] = dir.key.split("/")[1]

    my_keys = list(album_dict.keys())
    my_keys.sort()
    sorted_dict = {i: album_dict[i] for i in my_keys}

    if album_name_is_contains:
        if album_name[0] in my_keys:
            album_uuid = get_album_UUID(album_name)
            photo_list = photo_dict(album_uuid, True)

            if not photo_list:
                print(f"Photo not found in album {album_name}")
                exit(1)

        else:
            print(f'Photo album {album_name} not found')
            exit(1)
    else:

        if need_return:
            return sorted_dict

        if not album_dict:
            print('Photo albums not found')
            exit(1)

        for a in sorted_dict:
            print(a)
    exit(0)


def photo_dict(album_UUID, print_name=False):
    photo_dict = []

    for dir in admin_pub_bucket.objects.filter(Prefix=f"{PHOTO_NAME_PREFIX}/{album_UUID}"):
        photo_from_cloud_name = str(dir.get()['Body'].read().decode('utf-8'))
        photo_dict.append([dir.key.split("/")[2], photo_from_cloud_name])

    if print_name:
        for element in photo_dict:
            print(element[1])
        exit(0)

    return photo_dict


def create_new_album(name):
    album_new_uuid = uuid.uuid4()
    album_object = admin_resource.Object(BUCKET, f'{ALBUM_PREFIX}/{album_new_uuid}')
    album_object.put(Body=str.encode(name))
    return album_new_uuid


def create_new_photo(name, album_UUID):
    photo_uuid = uuid.uuid4()
    check_created_photo(name, album_UUID)
    photo_object = admin_resource.Object(BUCKET, f'{PHOTO_NAME_PREFIX}/{album_UUID}/{photo_uuid}')
    photo_object.put(Body=str.encode(name))
    return photo_uuid


def check_created_photo(photo_name, album_uuid):
    photo_dict_list = photo_dict(album_uuid)
    for photo_info in photo_dict_list:
        if photo_name == photo_info[1]:
            photo_uuid_for_delete = photo_info[0]
            delete_photo_and_name_file(photo_uuid_for_delete, album_uuid)
            break


def delete_photo_and_name_file(photo_uuid, album_uuid):
    for obj in admin_pub_bucket.objects.all():
        if album_uuid in obj.key:
            if photo_uuid in obj.key:
                obj.delete()


def photo_list_pair(album_uuid):
    photo_uri = get_album_photo(album_uuid)
    photo_data = []
    for photo_info in photo_uri:
        photo_info_split = photo_info.split("/")
        photo_name = photo_info_split[len(photo_info_split) - 1][:-2].split("\"")[2]
        photo_data.append([photo_info.split('\"')[1].split(BUCKET)[1][1:], photo_name])
    return photo_data


def get_album_UUID(album_name):
    if str("".join(album_name)) == '':
        print('The following arguments are required: ALBUM')
        exit(1)

    album_name_str = ""
    l = len(album_name)
    for i in range(l):
        if i == l - 1:
            album_name_str += album_name[i]
        else:
            album_name_str += album_name[i] + " "

    album_dicts = get_list(True, False)
    return album_dicts.get(album_name_str)


def delete():
    album_name = args.ALBUM
    album_uuid = get_album_UUID(album_name)
    photo_name = args.path

    find_photo = False

    if str(album_uuid) == 'None':
        print(f'Warning: Photo album not found <{str("".join(album_name))}>')
        exit(1)

    if photo_name is None:
        for obj in admin_pub_bucket.objects.all():
            if album_uuid in obj.key:
                obj.delete()
        exit(0)
    else:
        for obj in admin_pub_bucket.objects.all():
            if album_uuid in obj.key:
                if photo_name in obj.key:
                    find_photo = True
                    obj.delete()
        if find_photo:
            exit(0)
        else:
            print(f'Warning: Photo not found <{photo_name}>')
            exit(1)


def get_album_photo(album_uuid):
    album_list = []
    photo_dict_list = photo_dict(album_uuid)
    for photo_info in photo_dict_list:
        album_list.append(f"""<img src="{endpoint_url}/{BUCKET}/{PHOTO_PREFIX}/{album_uuid}/{photo_info[0]}" data-title="{photo_info[1]}">""")
    return album_list


def generate_error_html():
    html_object = admin_pub_bucket.Object('error.html')
    error_html_content = """<html>
    <head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
        <title>Фотоархив</title>
    </head>
<body>
    <h1>Ошибка</h1>
    <p>Ошибка при доступе к фотоархиву. Вернитесь на <a href="index.html">главную страницу</a> фотоархива.</p>
</body>
</html>"""
    html_object.put(Body=error_html_content, ContentType='text/html')


def generate_album_html():
    cloud_album_dict = get_list(True, False)
    index = 0
    for album in cloud_album_dict.values():
        index += 1
        album_photo = get_album_photo(album)
        html_object = admin_pub_bucket.Object(f'album{index}.html')
        album_html_content = f"""
                <!doctype html>
        <html>
            <head>
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
                <link rel="stylesheet" type="text/css" href="https://cdnjs.cloudflare.com/ajax/libs/galleria/1.6.1/themes/classic/galleria.classic.min.css" />
                <style>
                    .galleria{{ width: 960px; height: 540px; background: #000 }}
                </style>
                <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.6.0/jquery.min.js"></script>
                <script src="https://cdnjs.cloudflare.com/ajax/libs/galleria/1.6.1/galleria.min.js"></script>
                <script src="https://cdnjs.cloudflare.com/ajax/libs/galleria/1.6.1/themes/classic/galleria.classic.min.js"></script>
            </head>
            <body>
                <div class="galleria">
                {"".join(album_photo)}
                </div>
                <p>Вернуться на <a href="index.html">главную страницу</a> фотоархива</p>
                <script>
                    (function() {{
    Galleria.run('.galleria');
    }}());
                </script>
            </body>
        </html>
"""
        html_object.put(Body=album_html_content, ContentType='text/html')


def generate_index_html():
    html_object = admin_pub_bucket.Object('index.html')
    cloud_album_dict = get_list(True, False)
    album_items = []
    index = 0
    for album in cloud_album_dict.keys():
        index += 1
        album_items.append(f'<li><a href="album{index}.html">{album}</a></li>')
    html_content = f"""<!doctype html>
<html>
    <head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
        <title>Фотоархив</title>
    </head>
<body>
    <h1>Фотоархив</h1>
    <ul>
    {"".join(album_items)}
    </ul>
</body"""
    html_object.put(Body=html_content, ContentType='text/html')
    generate_album_html()
    generate_error_html()


def mksite():
    bucket_website = admin_pub_bucket.Website()
    index_document = {'Suffix': 'index.html'}
    error_document = {'Key': 'error.html'}
    bucket_website.put(WebsiteConfiguration={'ErrorDocument': error_document, 'IndexDocument': index_document})
    generate_index_html()
    print(f"https://{admin_pub_bucket.name}.website.yandexcloud.net")


def init():
    print("Enter aws_access_key_id:")
    aws_access_key_id = input()
    print("Enter aws_secret_access_key:")
    aws_secret_access_key = input()
    print("Enter bucket:")
    bucket = input()
    endpoint = "https://storage.yandexcloud.net"

    filename = f"{CONFIG_FILE_DIRECTORY}"
    if not os.path.exists(os.path.dirname(filename)):
        try:
            os.makedirs(os.path.dirname(filename))
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise

    with open(filename, "w") as f:
        f.write("[DEFAULT]\n")
        f.write(f"bucket = {bucket}\n")
        f.write(f"aws_access_key_id = {aws_access_key_id}\n")
        f.write(f"aws_secret_access_key = {aws_secret_access_key}\n")
        f.write("region = ru-central1\n")
        f.write("endpoint_url = https://storage.yandexcloud.net")
        f.close()

    user_session = boto3.session.Session(aws_access_key_id=aws_access_key_id,
                                         aws_secret_access_key=aws_secret_access_key)
    user_resource = user_session.resource(service_name='s3', endpoint_url=endpoint)
    user_pub_bucket = user_resource.Bucket(bucket)

    user_pub_bucket.create()
    user_pub_bucket.Acl().put(ACL='public-read')
    exit(0)


if action != "init":
    aws_access_key_id, aws_secret_access_key, BUCKET, region_name, endpoint_url = read_cred_from_config()
    admin_session, admin_resource, admin_pub_bucket = pre_init()

if action == "upload":
    upload()
elif action == "download":
    download()
elif action == "list":
    album_name = args.album is not None
    get_list(False, album_name)
elif action == "delete":
    delete()
elif action == "mksite":
    mksite()
elif action == "init":
    init()

